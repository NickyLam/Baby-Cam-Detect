"""Camera source validation and probing.

This module is the seam for camera-source handling. The current production
adapter validates RTSP sources only; future adapters can add ONVIF discovery,
brand cloud APIs, or local-video replay without changing camera API handlers.
"""
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

from app.core.url_security import redact_url_credentials


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    code: str
    message: str
    redacted_url: str


def redact_url(url: str) -> str:
    """Redact credentials embedded in a camera URL."""
    return redact_url_credentials(url)


class RTSPCameraConnector:
    """Validate local RTSP camera sources before they are stored or opened."""

    def validate_source(self, rtsp_url: str) -> ProbeResult:
        redacted = redact_url(rtsp_url)

        try:
            parsed = urlsplit(rtsp_url)
        except Exception:
            return ProbeResult(False, "invalid_url", "Camera URL is not parseable", redacted)

        if parsed.scheme.lower() != "rtsp":
            return ProbeResult(
                False,
                "unsupported_scheme",
                "Only RTSP camera sources are supported by this backend MVP",
                redacted,
            )

        if not parsed.hostname:
            return ProbeResult(False, "missing_host", "RTSP URL must include a host", redacted)

        try:
            host_ip = ip_address(parsed.hostname)
        except ValueError:
            return ProbeResult(
                False,
                "host_must_be_ip",
                "Use a LAN IP address for the camera host in this MVP",
                redacted,
            )

        if (
            host_ip.is_loopback
            or host_ip.is_link_local
            or host_ip.is_multicast
            or host_ip.is_unspecified
            or host_ip.is_reserved
        ):
            return ProbeResult(
                False,
                "blocked_host",
                "RTSP host is not an allowed LAN camera address",
                redacted,
            )

        if not host_ip.is_private:
            return ProbeResult(
                False,
                "non_lan_host",
                "Only private LAN camera addresses are accepted in this MVP",
                redacted,
            )

        return ProbeResult(True, "valid", "RTSP source accepted", redacted)
