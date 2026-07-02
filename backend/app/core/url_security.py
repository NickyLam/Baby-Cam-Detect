"""URL security helpers."""
from urllib.parse import urlsplit, urlunsplit


def redact_url_credentials(url: str) -> str:
    """Redact credentials embedded in a URL while preserving routing context."""
    try:
        parsed = urlsplit(url)
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return urlunsplit(
                (
                    parsed.scheme,
                    f"***:***@{host}",
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                )
            )
    except Exception:
        return "rtsp://***"
    return url
