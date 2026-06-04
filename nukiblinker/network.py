"""Network validation helpers — SSRF prevention for bridge clients."""

from __future__ import annotations

import ipaddress


def validate_local_ip(ip_str: str, label: str = "Bridge") -> str:
    """Validate that *ip_str* is a private/loopback/link-local IP.

    Returns the normalised (compressed) IP string.
    Raises ``ValueError`` for non-IP input or public addresses.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise ValueError(f"{label} IP must be a valid IP address") from exc

    if not (ip.is_private or ip.is_loopback or ip.is_link_local):
        raise ValueError(f"{label} IP must be in a local/private network range")

    return ip.compressed
