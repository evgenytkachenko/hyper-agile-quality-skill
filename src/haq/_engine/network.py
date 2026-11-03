"""Endpoint locality for the accidental remote-model-call guard; no DNS or network access."""

from ipaddress import ip_address


def is_loopback_host(hostname: str | None) -> bool:
    """Exact localhost or a literal loopback IP, never a hostname that merely looks like one.

    This classifies the configured address; it does not authenticate the service there.
    """
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False
