import re
from urllib.parse import urlparse

# Platforms with known, well-defined URL patterns. Only these are accepted
# until an extractor is implemented for them.
SUPPORTED_PLATFORMS = {
    "youtube": {
        "label": "YouTube",
        "hosts": [
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
        ],
        "pattern": re.compile(
            r"^/(watch\?v=[\w-]{6,}|shorts/[\w-]{6,}|embed/[\w-]{6,})|^/[\w-]{6,}$"
        ),
    },
    "vimeo": {
        "label": "Vimeo",
        "hosts": ["vimeo.com", "www.vimeo.com", "player.vimeo.com"],
        "pattern": re.compile(r"^/\d{6,}$"),
    },
    "dailymotion": {
        "label": "Dailymotion",
        "hosts": ["dailymotion.com", "www.dailymotion.com", "dai.ly"],
        "pattern": re.compile(r"^/video/[\w-]+|^/[\w-]+$"),
    },
    "facebook": {
        "label": "Facebook",
        "hosts": [
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
            "fb.watch",
            "fb.com",
            "www.fb.com",
        ],
        "pattern": re.compile(
            r"^/(watch|reel|share|videos?|video\.php|story\.php|permalink\.php|photo|posts|v/\d|\d+/videos)"
        ),
    },
    "twitter": {
        "label": "X (Twitter)",
        "hosts": [
            "x.com",
            "www.x.com",
            "twitter.com",
            "www.twitter.com",
            "m.twitter.com",
            "mobile.twitter.com",
        ],
        "pattern": re.compile(r"^/[\w.]+/status/\d+"),
    },
    "instagram": {
        "label": "Instagram",
        "hosts": ["instagram.com", "www.instagram.com", "m.instagram.com"],
        "pattern": re.compile(r"^/(reel|reels|p|tv|stories|share|embed)/"),
    },
    "tiktok": {
        "label": "TikTok",
        "hosts": [
            "tiktok.com",
            "www.tiktok.com",
            "m.tiktok.com",
            "vm.tiktok.com",
            "vt.tiktok.com",
        ],
        "pattern": re.compile(r"^/@[\w.]+/video/\d+|^/[\w-]{6,}$"),
    },
    "twitch": {
        "label": "Twitch",
        "hosts": ["twitch.tv", "www.twitch.tv", "m.twitch.tv"],
        "pattern": re.compile(r"^/videos/\d+|^/[\w]+(?:/clip/[\w-]+)?$"),
    },
    "reddit": {
        "label": "Reddit",
        "hosts": ["reddit.com", "www.reddit.com", "old.reddit.com", "redd.it"],
        "pattern": re.compile(
            r"^/r/[\w.]+/comments/[\w,]+|^/[\w,]+$"
        ),
    },
}


class ValidationError(Exception):
    """Raised when a submitted link cannot be accepted."""

    def __init__(self, message, code="invalid_link"):
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_url(raw):
    """Trim and require an explicit http(s) scheme."""
    if not isinstance(raw, str):
        raise ValidationError("Please provide a link as text.", "missing_link")
    url = raw.strip()
    if not url:
        raise ValidationError("Please paste a video link first.", "missing_link")
    if len(url) > 2048:
        raise ValidationError("That link is too long.", "link_too_long")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def validate_link(raw):
    """Validate a video link and return platform metadata.

    Returns a dict: {"url", "platform", "platform_label"}.
    Raises ValidationError with a user-facing message otherwise.
    """
    url = normalize_url(raw)
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Only http and https links are supported.", "bad_scheme")

    host = (parsed.hostname or "").lower()
    if not host:
        raise ValidationError("That link is missing a domain name.", "bad_host")

    platform = None
    for key, info in SUPPORTED_PLATFORMS.items():
        if host in info["hosts"]:
            platform = key
            break

    if platform is None:
        raise ValidationError(
            "That site isn't supported yet. Try YouTube, Facebook, X, Instagram, "
            "TikTok, Twitch, Reddit, Vimeo or Dailymotion.",
            "unsupported_platform",
        )

    info = SUPPORTED_PLATFORMS[platform]
    path = parsed.path or "/"
    # Include the query string so watch-style URLs (?v=<id>) match.
    target = path + (("?" + parsed.query) if parsed.query else "")
    # Short links (youtu.be/<id>) only have an opaque path; pattern applies to target.
    short_link_hosts = {
        "youtu.be",
        "dai.ly",
        "fb.watch",
        "redd.it",
        "vm.tiktok.com",
        "vt.tiktok.com",
    }
    is_short_link = host in short_link_hosts
    if not is_short_link and not info["pattern"].search(target):
        raise ValidationError(
            f"That doesn't look like a valid {info['label']} video link.",
            "invalid_video_url",
        )

    if is_short_link and len(path.strip("/")) < 3:
        raise ValidationError(
            f"That doesn't look like a valid {info['label']} video link.",
            "invalid_video_url",
        )

    return {
        "url": url,
        "platform": platform,
        "platform_label": info["label"],
    }
