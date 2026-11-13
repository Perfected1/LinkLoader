import os
import shutil

from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request, stream_with_context

from .ai_clips import suggest_clips
from .extractor import (
    ExtractionError,
    download_video,
    fetch_formats,
    fetch_video_info,
    trim_video,
)
from .validation import ValidationError, validate_link

bp = Blueprint("main", __name__, url_prefix="/api")

MAX_CLIP_SECONDS = 6 * 60 * 60


def _error(message, code, status=400):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


def _clip_seconds(value):
    """Normalise one clip boundary to seconds, or None when it is omitted."""
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValidationError("Enter clip times as seconds.", "invalid_clip")
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise ValidationError("Enter clip times as seconds.", "invalid_clip")
    if seconds != seconds or seconds in (float("inf"), float("-inf")):
        raise ValidationError("Enter valid clip times.", "invalid_clip")
    return seconds


def parse_clip(payload):
    """Return (start, end) seconds for a requested clip, or None for full video."""
    start = _clip_seconds(payload.get("start"))
    end = _clip_seconds(payload.get("end"))

    if start is None and end is None:
        return None
    if start is None:
        start = 0.0
    if end is None:
        raise ValidationError(
            "Enter an end time for the clip, or clear the start time.", "invalid_clip"
        )
    if start < 0:
        raise ValidationError(
            "The clip start time cannot be negative.", "invalid_clip"
        )
    if end <= start:
        raise ValidationError(
            "The clip end time must be after the start time.", "invalid_clip"
        )
    if end - start < 1:
        raise ValidationError("Clips must be at least 1 second long.", "invalid_clip")
    if end > MAX_CLIP_SECONDS:
        raise ValidationError(
            "That clip is too long. Choose a range under 6 hours.", "invalid_clip"
        )
    return start, end


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@bp.route("/validate", methods=["POST"])
def validate():
    payload = request.get_json(silent=True) or {}
    try:
        result = validate_link(payload.get("url"))
    except ValidationError as exc:
        return _error(exc.message, exc.code)
    return jsonify({"ok": True, "data": result})


@bp.route("/info", methods=["POST"])
def info():
    payload = request.get_json(silent=True) or {}
    try:
        link = validate_link(payload.get("url"))
    except ValidationError as exc:
        return _error(exc.message, exc.code)

    try:
        data = fetch_video_info(link["url"])
    except ExtractionError as exc:
        status = 504 if exc.code == "timeout" else 422
        return _error(exc.message, exc.code, status)

    data["platform"] = link["platform"]
    data["platform_label"] = link["platform_label"]
    return jsonify({"ok": True, "data": data})


@bp.route("/formats", methods=["POST"])
def formats():
    payload = request.get_json(silent=True) or {}
    try:
        link = validate_link(payload.get("url"))
    except ValidationError as exc:
        return _error(exc.message, exc.code)

    try:
        data = fetch_formats(link["url"])
    except ExtractionError as exc:
        status = 504 if exc.code == "timeout" else 422
        return _error(exc.message, exc.code, status)

    return jsonify({"ok": True, "data": data})


@bp.route("/ai/clips", methods=["POST"])
def ai_clips():
    payload = request.get_json(silent=True) or {}
    try:
        link = validate_link(payload.get("url"))
    except ValidationError as exc:
        return _error(exc.message, exc.code)

    prompt = payload.get("prompt") or ""
    if not isinstance(prompt, str):
        return _error("Describe the moment you want as text.", "invalid_prompt")
    prompt = prompt.strip()[:300]

    try:
        duration = _clip_seconds(payload.get("duration"))
    except ValidationError as exc:
        return _error(exc.message, exc.code)
    if duration is not None and duration <= 0:
        duration = None

    try:
        data = suggest_clips(link["url"], prompt=prompt, duration=duration)
    except ExtractionError as exc:
        if exc.code == "ai_not_configured":
            status = 503
        elif exc.code in ("timeout", "ai_timeout"):
            status = 504
        elif exc.code == "ai_rate_limited":
            status = 429
        else:
            status = 422
        return _error(exc.message, exc.code, status)

    return jsonify({"ok": True, "data": data})


@bp.route("/download", methods=["POST"])
def download():
    payload = request.get_json(silent=True) or {}
    try:
        link = validate_link(payload.get("url"))
    except ValidationError as exc:
        return _error(exc.message, exc.code)

    raw_height = payload.get("height")
    if raw_height in (None, "", "best"):
        height = None
    else:
        try:
            height = int(raw_height)
        except (TypeError, ValueError):
            return _error("Choose a valid video quality.", "invalid_quality")
        if not 144 <= height <= 4320:
            return _error("Choose a valid video quality.", "invalid_quality")

    try:
        clip = parse_clip(payload)
    except ValidationError as exc:
        return _error(exc.message, exc.code)

    try:
        path, filename, temp_dir = download_video(link["url"], height)
    except ExtractionError as exc:
        status = 504 if exc.code == "download_timeout" else 422
        return _error(exc.message, exc.code, status)

    if clip:
        try:
            path, filename = trim_video(path, filename, clip[0], clip[1])
        except ExtractionError as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            status = 504 if exc.code == "clip_timeout" else 422
            return _error(exc.message, exc.code, status)

    def stream_file():
        try:
            with open(path, "rb") as handle:
                while True:
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    ascii_name = filename.encode("ascii", "ignore").decode() or "video.mp4"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(filename)}"
        ),
        "Content-Length": str(os.path.getsize(path)),
        "Cache-Control": "no-store",
    }
    return Response(
        stream_with_context(stream_file()),
        mimetype="video/mp4",
        headers=headers,
    )
