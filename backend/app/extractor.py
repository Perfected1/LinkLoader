"""Video metadata extraction built on yt-dlp.

Only metadata is read here; nothing is downloaded until the user explicitly
asks for it in the download step.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

YTDLP_TIMEOUT = 45
DOWNLOAD_TIMEOUT = 300
CLIP_TIMEOUT = 300


class ExtractionError(Exception):
    def __init__(self, message, code="extraction_failed"):
        super().__init__(message)
        self.message = message
        self.code = code


def _ffmpeg_location():
    """Prefer a system ffmpeg, otherwise fall back to the bundled binary."""
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _run_ytdlp(url, extra_args=None):
    """Run yt-dlp and return parsed JSON metadata."""
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--skip-download",
        "--no-warnings",
        "--dump-single-json",
        url,
    ]
    if extra_args:
        cmd[3:3] = extra_args

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=YTDLP_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise ExtractionError(
            "Reading this video took too long. Please try again.", "timeout"
        )
    except FileNotFoundError:
        raise ExtractionError(
            "The video extractor is not available on the server.", "extractor_missing"
        )

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else ""
        if "Private video" in reason or "private" in reason.lower():
            raise ExtractionError(
                "This video is private and cannot be accessed.", "private_video"
            )
        if "age" in reason.lower() and "restrict" in reason.lower():
            raise ExtractionError(
                "This video is age-restricted and cannot be accessed.", "age_restricted"
            )
        if "not available" in reason.lower() or "unavailable" in reason.lower():
            raise ExtractionError(
                "This video is not available. It may have been removed.",
                "video_unavailable",
            )
        lowered = "\n".join(detail).lower()
        if (
            "login" in lowered
            or "sign-in" in lowered
            or "cookies" in lowered
            or "logged-in" in lowered
        ):
            raise ExtractionError(
                "This post may be private or require sign-in. Try a public link.",
                "login_required",
            )
        raise ExtractionError(
            "Could not read this video's details. Check the link and try again."
        )

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ExtractionError("The video data could not be read. Please try again.")


def _format_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return None
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _pick_quality_options(raw):
    """Reduce raw yt-dlp formats to one selectable entry per resolution."""
    best_by_height = {}
    for fmt in raw.get("formats") or []:
        if fmt.get("vcodec") in (None, "none"):
            continue
        height = fmt.get("height")
        if not height:
            continue
        # Skip storyboards and other non-video artifacts.
        if fmt.get("format_note") == "storyboard" or fmt.get("ext") == "mhtml":
            continue
        current = best_by_height.get(height)
        score = (fmt.get("ext") == "mp4", fmt.get("tbr") or 0)
        if current is None or score > current[0]:
            best_by_height[height] = (score, fmt)

    options = []
    for height in sorted(best_by_height, reverse=True):
        fmt = best_by_height[height][1]
        options.append(
            {
                "height": height,
                "label": f"{height}p",
                "ext": fmt.get("ext"),
                "fps": fmt.get("fps"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
            }
        )
    return options


def fetch_formats(url):
    """Return selectable video qualities for a validated link."""
    raw = _run_ytdlp(url)
    options = _pick_quality_options(raw)
    if not options:
        raise ExtractionError(
            "No downloadable video qualities were found for this link.",
            "no_formats",
        )
    return {
        "title": raw.get("title") or "video",
        "duration_seconds": raw.get("duration"),
        "options": options,
    }


def _sanitize_filename(name, fallback="video"):
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name or "").strip().strip(".")
    safe = re.sub(r"\s+", " ", safe)[:150]
    return safe or fallback


def download_video(url, height=None):
    """Download a video at the requested height (or best) into a temp dir.

    Returns (path, filename, temp_dir). The caller is responsible for
    deleting temp_dir once the response has been sent.
    """
    temp_dir = tempfile.mkdtemp(prefix="linkload-")
    output_template = os.path.join(temp_dir, "%(title).150B.%(ext)s")

    if height:
        selector = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        )
    else:
        selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        "--merge-output-format",
        "mp4",
        "-f",
        selector,
        "-o",
        output_template,
    ]

    ffmpeg = _ffmpeg_location()
    if ffmpeg:
        cmd.extend(["--ffmpeg-location", ffmpeg])
    cmd.append(url)

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ExtractionError(
            "The download took too long. Try a lower quality or another link.",
            "download_timeout",
        )

    if proc.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        detail = (proc.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else ""
        if "Private video" in reason:
            raise ExtractionError(
                "This video is private and cannot be downloaded.", "private_video"
            )
        raise ExtractionError(
            "The download could not be completed. The video may be restricted.",
            "download_failed",
        )

    files = [
        os.path.join(temp_dir, f)
        for f in os.listdir(temp_dir)
        if not f.endswith(".part")
    ]
    if not files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ExtractionError("The download produced no file.", "download_failed")

    path = max(files, key=os.path.getsize)
    filename = _sanitize_filename(os.path.splitext(os.path.basename(path))[0])
    ext = os.path.splitext(path)[1] or ".mp4"
    return path, f"{filename}{ext}", temp_dir


def _time_label(seconds):
    """Compact human label for a clip boundary, e.g. 1m05s or 1h02m30s."""
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


def trim_video(source_path, filename, start, end):
    """Cut the [start, end) seconds of a downloaded file into its own MP4.

    The clip is re-encoded so the cut lands on the exact requested times.
    Returns (path, filename). The caller owns cleanup of the temp directory.
    """
    ffmpeg = _ffmpeg_location()
    if not ffmpeg:
        raise ExtractionError(
            "Clipping is not available on the server. Download the full video instead.",
            "clip_unavailable",
        )

    base = os.path.splitext(filename)[0]
    clip_name = f"{base} (clip {_time_label(start)}-{_time_label(end)}).mp4"
    target = source_path + ".clip.mp4"

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        f"{start:.3f}",
        "-i",
        source_path,
        "-t",
        f"{end - start:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-y",
        target,
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=CLIP_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise ExtractionError(
            "Creating that clip took too long. Try a shorter range.", "clip_timeout"
        )
    except OSError:
        raise ExtractionError(
            "Clipping is not available on the server. Download the full video instead.",
            "clip_unavailable",
        )

    if proc.returncode != 0 or not os.path.isfile(target) or os.path.getsize(target) == 0:
        raise ExtractionError(
            "That clip could not be created. Check the start and end times.",
            "clip_failed",
        )

    return target, clip_name


def fetch_video_info(url):
    """Return preview metadata for a validated video link."""
    raw = _run_ytdlp(url)

    title = raw.get("title") or "Untitled video"
    uploader = raw.get("uploader") or raw.get("channel") or None
    thumbnail = raw.get("thumbnail")
    if not thumbnail:
        thumbs = raw.get("thumbnails") or []
        if thumbs:
            thumbnail = thumbs[-1].get("url")

    return {
        "id": raw.get("id"),
        "title": title,
        "uploader": uploader,
        "duration_seconds": raw.get("duration"),
        "duration": _format_duration(raw.get("duration")),
        "thumbnail": thumbnail,
        "webpage_url": raw.get("webpage_url") or url,
        "is_live": bool(raw.get("is_live")),
    }
