import os
import subprocess
import tempfile

import pytest

from app import create_app
from app.ai_clips import fetch_transcript, normalise_clips, parse_vtt
from app.extractor import (
    ExtractionError,
    _ffmpeg_location,
    _pick_quality_options,
    trim_video,
)
from app.main import parse_clip
from app.validation import ValidationError, validate_link


@pytest.fixture()
def client():
    app = create_app({"TESTING": True})
    return app.test_client()


@pytest.mark.parametrize(
    "url, platform",
    [
        ("https://www.youtube.com/watch?v=jNQXAC9IVRw", "youtube"),
        ("https://youtu.be/jNQXAC9IVRw", "youtube"),
        ("https://www.youtube.com/shorts/abc123xyz", "youtube"),
        ("https://vimeo.com/22439234", "vimeo"),
        ("https://www.dailymotion.com/video/x8abcde", "dailymotion"),
        ("youtube.com/watch?v=jNQXAC9IVRw", "youtube"),
        (
            "https://www.facebook.com/watch/?v=1234567890123456",
            "facebook",
        ),
        (
            "https://www.facebook.com/reel/1234567890123456",
            "facebook",
        ),
        ("https://fb.watch/AbCdEfGhIj/", "facebook"),
        (
            "https://x.com/jawed/status/1234567890123456789",
            "twitter",
        ),
        (
            "https://twitter.com/jawed/status/1234567890123456789?s=20",
            "twitter",
        ),
        ("https://www.instagram.com/reel/abcDEF12345/", "instagram"),
        ("https://www.instagram.com/p/abcDEF12345/", "instagram"),
        (
            "https://www.tiktok.com/@creator/video/7123456789012345678",
            "tiktok",
        ),
        ("https://vm.tiktok.com/ZMbAbCdEf/", "tiktok"),
        ("https://www.twitch.tv/videos/123456789", "twitch"),
        ("https://www.twitch.tv/somechannel", "twitch"),
        (
            "https://www.reddit.com/r/videos/comments/abc1234/some_title/",
            "reddit",
        ),
        ("https://redd.it/abc1234", "reddit"),
    ],
)
def test_validate_link_accepts_supported_urls(url, platform):
    result = validate_link(url)
    assert result["platform"] == platform
    assert result["url"].startswith("https://")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        None,
        "https://example.com/watch?v=abc123",
        "https://www.youtube.com/",
        "https://vimeo.com/not-a-video",
        "https://x.com/home",
        "https://x.com/someuser",
        "https://www.instagram.com/",
        "https://www.facebook.com/",
        "https://www.twitch.tv/",
        "https://www.tiktok.com/",
        "https://www.reddit.com/",
        "https://fb.watch/",
        "https://redd.it/",
        "https://twitter.com/jawed",
    ],
)
def test_validate_link_rejects_bad_urls(url):
    with pytest.raises(ValidationError):
        validate_link(url)


def test_validate_endpoint_shape(client):
    ok = client.post("/api/validate", json={"url": "https://youtu.be/jNQXAC9IVRw"})
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["ok"] is True
    assert body["data"]["platform_label"] == "YouTube"

    bad = client.post("/api/validate", json={"url": "https://example.com/x"})
    assert bad.status_code == 400
    body = bad.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "unsupported_platform"
    assert body["error"]["message"]


def test_pick_quality_options_dedupes_and_skips_audio():
    raw = {
        "formats": [
            {"height": 720, "ext": "webm", "vcodec": "vp9", "tbr": 2000},
            {"height": 720, "ext": "mp4", "vcodec": "avc1", "tbr": 1500},
            {"height": 1080, "ext": "mp4", "vcodec": "avc1", "tbr": 4000},
            {"height": None, "ext": "m4a", "vcodec": "none", "tbr": 128},
            {"height": 144, "ext": "mhtml", "vcodec": "none", "format_note": "storyboard"},
        ]
    }
    options = _pick_quality_options(raw)
    assert [o["height"] for o in options] == [1080, 720]
    assert options[1]["ext"] == "mp4"  # mp4 preferred over higher-bitrate webm


def test_formats_endpoint_returns_options(client, monkeypatch):
    monkeypatch.setattr(
        "app.main.fetch_formats",
        lambda url: {
            "title": "Demo",
            "duration_seconds": 30,
            "options": [{"height": 720, "label": "720p", "ext": "mp4"}],
        },
    )
    response = client.post("/api/formats", json={"url": "https://youtu.be/jNQXAC9IVRw"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["options"][0]["label"] == "720p"


def test_formats_endpoint_maps_extraction_error(client, monkeypatch):
    def boom(url):
        raise ExtractionError("No qualities.", "no_formats")

    monkeypatch.setattr("app.main.fetch_formats", boom)
    response = client.post("/api/formats", json={"url": "https://youtu.be/jNQXAC9IVRw"})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "no_formats"


def test_download_streams_file_and_cleans_up(client, monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="linkload-test-")
    path = os.path.join(temp_dir, "Clip.mp4")
    payload = b"\x00\x00\x00\x20ftypisom" + b"video-bytes" * 10
    with open(path, "wb") as handle:
        handle.write(payload)

    monkeypatch.setattr(
        "app.main.download_video",
        lambda url, height=None: (path, "Clip.mp4", temp_dir),
    )

    response = client.post(
        "/api/download",
        json={"url": "https://youtu.be/jNQXAC9IVRw", "height": 720},
    )
    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype == "video/mp4"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "Clip.mp4" in response.headers["Content-Disposition"]
    assert response.headers["Content-Length"] == str(len(payload))
    assert not os.path.exists(temp_dir)


def test_download_rejects_invalid_quality(client):
    response = client.post(
        "/api/download",
        json={"url": "https://youtu.be/jNQXAC9IVRw", "height": "huge"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_quality"


def test_download_error_response_is_json(client, monkeypatch):
    def boom(url, height=None):
        raise ExtractionError("This video is private and cannot be downloaded.", "private_video")

    monkeypatch.setattr("app.main.download_video", boom)
    response = client.post(
        "/api/download", json={"url": "https://youtu.be/jNQXAC9IVRw", "height": "best"}
    )
    assert response.status_code == 422
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "private_video"


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({}, None),
        ({"start": None, "end": None}, None),
        ({"start": None, "end": ""}, None),
        ({"start": "10", "end": "25.5"}, (10.0, 25.5)),
        ({"start": 0, "end": 12}, (0.0, 12.0)),
        ({"end": 40}, (0.0, 40.0)),
    ],
)
def test_parse_clip_accepts_valid_ranges(payload, expected):
    assert parse_clip(payload) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"start": "abc", "end": 20},
        {"start": 10},
        {"start": 20, "end": 20},
        {"start": 20, "end": 10},
        {"start": 0, "end": 0.5},
        {"start": -5, "end": 10},
        {"start": 0, "end": 7 * 60 * 60},
        {"start": True, "end": 10},
        {"start": float("nan"), "end": 10},
        {"start": [1], "end": 10},
    ],
)
def test_parse_clip_rejects_bad_ranges(payload):
    with pytest.raises(ValidationError) as exc:
        parse_clip(payload)
    assert exc.value.code == "invalid_clip"


def test_download_rejects_invalid_clip(client, monkeypatch):
    def unexpected(url, height=None):
        raise AssertionError("download should not start for an invalid clip")

    monkeypatch.setattr("app.main.download_video", unexpected)
    response = client.post(
        "/api/download",
        json={"url": "https://youtu.be/jNQXAC9IVRw", "start": 30, "end": 10},
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "invalid_clip"
    assert body["error"]["message"]


def test_download_trims_requested_clip(client, monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-bytes")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip-bytes")

    monkeypatch.setattr(
        "app.main.download_video",
        lambda url, height=None: (str(source), "Clip.mp4", str(tmp_path)),
    )
    calls = {}

    def fake_trim(path, filename, start, end):
        calls["args"] = (path, filename, start, end)
        return str(clip), "Clip (clip 0m10s-0m20s).mp4"

    monkeypatch.setattr("app.main.trim_video", fake_trim)

    response = client.post(
        "/api/download",
        json={"url": "https://youtu.be/jNQXAC9IVRw", "height": 720, "start": 10, "end": 20},
    )

    assert response.status_code == 200
    assert response.data == b"clip-bytes"
    assert calls["args"] == (str(source), "Clip.mp4", 10.0, 20.0)
    assert "0m10s-0m20s" in response.headers["Content-Disposition"]
    assert response.headers["Content-Length"] == str(len(b"clip-bytes"))
    assert not tmp_path.exists()  # temp dir removed once the stream ends


@pytest.mark.skipif(_ffmpeg_location() is None, reason="ffmpeg is not available")
def test_trim_video_cuts_requested_range(tmp_path):
    ffmpeg = _ffmpeg_location()
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=6:size=160x120:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    path, name = trim_video(str(source), "Demo.mp4", 2, 4)

    assert name == "Demo (clip 0m02s-0m04s).mp4"
    assert os.path.getsize(path) > 0
    probe = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    assert "Duration: 00:00:02" in probe.stderr


def test_parse_vtt_keeps_cues_and_drops_rolling_repeats():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
hello and welcome

00:00:03.000 --> 00:00:05.000
hello and welcome
to the demo

00:00:05.000 --> 00:00:07.000
<v Speaker>here we go</v>

00:00:07.000 --> 00:00:09.000
here we go
"""
    assert parse_vtt(vtt) == [
        (1, "hello and welcome"),
        (3, "to the demo"),
        (5, "here we go"),
    ]


def test_fetch_transcript_without_subtitles_raises(monkeypatch):
    class Completed:
        returncode = 0

    monkeypatch.setattr(
        "app.ai_clips.subprocess.run", lambda *args, **kwargs: Completed()
    )
    with pytest.raises(ExtractionError) as exc:
        fetch_transcript("https://youtu.be/jNQXAC9IVRw")
    assert exc.value.code == "no_transcript"


def test_normalise_clips_clamps_to_duration_and_filters_bad_ranges():
    raw = {
        "clips": [
            {"start": 10, "end": 20, "title": "Good", "reason": "Sets it up"},
            {"start": 30, "end": 100, "title": "Runs past the end"},
            {"start": 40, "end": 30, "title": "Backwards"},
            {"start": "early", "end": 5, "title": "Not a number"},
            {"start": 50, "end": 55.5, "title": "Last"},
        ]
    }
    clips = normalise_clips(raw, duration=60, limit=3)
    assert [(c["start"], c["end"]) for c in clips] == [
        (10.0, 20.0),
        (30.0, 60.0),
        (50.0, 55.5),
    ]
    assert clips[0]["reason"] == "Sets it up"


def test_normalise_clips_requires_a_usable_clip():
    with pytest.raises(ExtractionError) as exc:
        normalise_clips({"clips": []}, duration=60)
    assert exc.value.code == "ai_no_clips"


def test_ai_clips_endpoint_forwards_request(client, monkeypatch):
    captured = {}

    def fake_suggest(url, prompt="", duration=None):
        captured.update(url=url, prompt=prompt, duration=duration)
        return {
            "clips": [
                {"start": 4.0, "end": 19.5, "title": "The demo", "reason": "Shows it"}
            ],
            "prompt": bool(prompt),
        }

    monkeypatch.setattr("app.main.suggest_clips", fake_suggest)
    response = client.post(
        "/api/ai/clips",
        json={
            "url": "https://youtu.be/jNQXAC9IVRw",
            "prompt": "  the demo  ",
            "duration": 120,
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["clips"][0]["title"] == "The demo"
    assert data["prompt"] is True
    assert captured == {
        "url": "https://youtu.be/jNQXAC9IVRw",
        "prompt": "the demo",
        "duration": 120.0,
    }


def test_ai_clips_endpoint_maps_missing_configuration(client, monkeypatch):
    def boom(url, prompt="", duration=None):
        raise ExtractionError("AI clipping isn't set up on this server.", "ai_not_configured")

    monkeypatch.setattr("app.main.suggest_clips", boom)
    response = client.post(
        "/api/ai/clips", json={"url": "https://youtu.be/jNQXAC9IVRw"}
    )
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "ai_not_configured"


def test_ai_clips_endpoint_rejects_non_text_prompt(client):
    response = client.post(
        "/api/ai/clips", json={"url": "https://youtu.be/jNQXAC9IVRw", "prompt": [1]}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_prompt"


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
