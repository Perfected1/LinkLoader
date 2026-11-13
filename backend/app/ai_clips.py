"""AI clip suggestions.

The video's subtitles are downloaded (no media), turned into a timestamped
transcript and sent to Gemini, which returns standalone clip ranges. Highlight
mode picks the best moments; prompt mode finds the moment the user describes.
"""

import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile

import requests

from .extractor import YTDLP_TIMEOUT, ExtractionError

AI_TIMEOUT = 60
DEFAULT_MODEL = "gemini-3.8-flash"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
MAX_TRANSCRIPT_CHARS = 150_000

TIMESTAMP = re.compile(r"^(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})$")


def _parse_timestamp(value):
    match = TIMESTAMP.match(value.strip())
    if not match:
        return None
    hours, minutes, seconds, _millis = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def _clean_caption(text):
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_vtt(text):
    """Turn WebVTT into [(start_seconds, text)], dropping rolling repeats."""
    cues = []
    start = None
    parts = []

    def flush():
        nonlocal start, parts
        if start is not None and parts:
            cues.append((start, " ".join(parts)))
        start, parts = None, []

    for raw in text.splitlines():
        line = raw.strip()
        if "-->" in line:
            flush()
            start = _parse_timestamp(line.split("-->")[0].strip())
            continue
        if not line:
            flush()
            continue
        if line.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        if start is not None:
            cleaned = _clean_caption(line)
            if cleaned:
                parts.append(cleaned)
    flush()

    segments = []
    previous = ""
    for cue_start, caption in cues:
        if caption == previous:
            continue
        # Auto captions repeat the previous line; keep only the new words.
        if previous and caption.startswith(previous):
            caption = caption[len(previous) :].strip()
        if not caption:
            continue
        segments.append((cue_start, caption))
        previous = caption
    return segments


def _transcript_text(segments):
    lines = [f"[{int(start)}s] {text}" for start, text in segments]
    transcript = "\n".join(lines)
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "\n[transcript truncated]"
    return transcript


def fetch_transcript(url, lang="en"):
    """Download and parse the video's subtitles, preferring English."""
    temp_dir = tempfile.mkdtemp(prefix="linkload-subs-")
    try:
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            f"{lang}.*,{lang}",
            "--sub-format",
            "vtt",
            "--no-warnings",
            "-o",
            os.path.join(temp_dir, "%(id)s.%(ext)s"),
            url,
        ]
        try:
            subprocess.run(
                cmd, capture_output=True, text=True, timeout=YTDLP_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            raise ExtractionError(
                "Reading this video's subtitles took too long. Please try again.",
                "timeout",
            )
        except OSError:
            raise ExtractionError(
                "The subtitle reader is not available on the server.",
                "extractor_missing",
            )

        files = sorted(glob.glob(os.path.join(temp_dir, "*.vtt")))
        if not files:
            raise ExtractionError(
                "This video has no subtitles, so AI clipping isn't available for it.",
                "no_transcript",
            )

        segments = []
        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    segments = parse_vtt(handle.read())
            except OSError:
                continue
            if segments:
                break

        if not segments:
            raise ExtractionError(
                "This video's subtitles could not be read, so AI clipping isn't available.",
                "no_transcript",
            )

        return {"segments": segments, "text": _transcript_text(segments)}
    finally:
        for path in glob.glob(os.path.join(temp_dir, "*")):
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass


def _load_json(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise ExtractionError(
        "The AI returned an unexpected answer. Please try again.", "ai_failed"
    )


def _call_gemini(system_prompt, user_prompt):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ExtractionError(
            "AI clipping isn't set up on this server. Add GEMINI_API_KEY and restart.",
            "ai_not_configured",
        )
    model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    try:
        response = requests.post(
            GEMINI_ENDPOINT.format(model=model),
            json=payload,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=AI_TIMEOUT,
        )
    except requests.Timeout:
        raise ExtractionError(
            "The AI took too long to analyse this video. Please try again.",
            "ai_timeout",
        )
    except requests.RequestException:
        raise ExtractionError(
            "Could not reach the AI service. Please try again in a moment.",
            "ai_unavailable",
        )

    if response.status_code == 429:
        raise ExtractionError(
            "The AI service is rate-limited right now. Try again in a minute.",
            "ai_rate_limited",
        )
    if response.status_code in (401, 403) or (
        response.status_code == 400 and "API key" in response.text
    ):
        raise ExtractionError(
            "The AI service rejected the API key. Set a valid GEMINI_API_KEY.",
            "ai_not_configured",
        )
    if response.status_code >= 400:
        raise ExtractionError(
            "The AI service could not analyse this video. Please try again.",
            "ai_failed",
        )

    try:
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ExtractionError(
            "The AI returned no suggestions for this video.", "ai_failed"
        )
    return _load_json(text)


def normalise_clips(raw, duration=None, limit=5):
    """Keep only usable clip ranges and trim them to the video's length."""
    clips = raw.get("clips") if isinstance(raw, dict) else raw
    if not isinstance(clips, list):
        raise ExtractionError(
            "The AI returned no suggestions for this video.", "ai_failed"
        )

    result = []
    for item in clips:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if start != start or end != end:
            continue
        start = max(0.0, start)
        if duration:
            start = min(start, float(duration))
            end = min(end, float(duration))
        if end <= start or end - start < 1:
            continue

        title = str(item.get("title") or "Clip").strip()[:80] or "Clip"
        reason = str(item.get("reason") or "").strip()[:200]
        result.append(
            {
                "start": round(start, 1),
                "end": round(end, 1),
                "title": title,
                "reason": reason,
            }
        )
        if len(result) >= limit:
            break

    if not result:
        raise ExtractionError(
            "The AI couldn't find a suitable clip in this video. Try a different request.",
            "ai_no_clips",
        )
    return result


SYSTEM_PROMPT = (
    "You are a video editor selecting short, standalone clips from a video "
    "transcript. Transcript lines look like '[SECONDS] text', where SECONDS is "
    "the second the line starts. Choose moments that make sense without the rest "
    "of the video, and use only timestamps that appear in the transcript. "
    "Reply with JSON only, no markdown, in exactly this shape: "
    '{"clips": [{"start": 12.0, "end": 48.5, "title": "short title", '
    '"reason": "one sentence on why this moment works"}]}'
)


def suggest_clips(url, prompt="", duration=None, count=5):
    """Return AI-selected clip ranges for a video link."""
    transcript = fetch_transcript(url)
    count = max(1, min(int(count or 5), 8))

    if prompt:
        task = (
            f'The viewer wants this moment: "{prompt}". '
            f"Return 1 to {count} clips that best match it, shortest useful range."
        )
    else:
        task = f"Choose the {count} most interesting, self-contained moments."

    hint = (
        "Aim for 15 to 90 second clips, but keep a clip shorter if the whole "
        "thought fits in less."
    )
    if duration:
        hint += f" The video is {int(duration)} seconds long; never go past that."

    user_prompt = (
        f"{task} {hint}\n\nTranscript:\n{transcript['text']}"
    )
    raw = _call_gemini(SYSTEM_PROMPT, user_prompt)
    return {
        "clips": normalise_clips(raw, duration=duration, limit=count),
        "prompt": bool(prompt),
    }
