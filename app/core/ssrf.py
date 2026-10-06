"""SSRF protection for every outbound fetch.

validate_url() parses the URL, resolves DNS, and rejects anything that is not a public
http/https address on port 80/443. Callers must call it again after every redirect.
"""

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
MAX_URL_LENGTH = 2048

# Networks that is_global does not already cover, or that we want to name explicitly.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network(n)
    for n in (
        "169.254.0.0/16",  # link-local + cloud metadata (169.254.169.254)
        "100.64.0.0/10",  # carrier-grade NAT
        "192.0.0.0/24",
        "198.18.0.0/15",
        "fd00:ec2::/32",  # AWS IPv6 metadata
        "fe80::/10",
        "fc00::/7",
    )
]

Resolver = Callable[[str, int], list[str]]


class SSRFError(ValueError):
    """The URL was rejected by the SSRF filter."""


@dataclass(frozen=True)
class SafeTarget:
    url: str
    scheme: str
    host: str
    port: int
    ip: str  # validated address to connect to


def default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def is_blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%")[0])
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if not ip.is_global:
        return True
    return any(ip in net for net in _BLOCKED_NETWORKS)


def validate_url(url: str, resolver: Resolver = default_resolver) -> SafeTarget:
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise SSRFError("invalid URL")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise SSRFError("invalid URL") from exc
    if parts.scheme not in ALLOWED_SCHEMES:
        raise SSRFError("only http and https are allowed")
    if parts.username or parts.password:
        raise SSRFError("credentials in URL are not allowed")
    host = parts.hostname
    if not host:
        raise SSRFError("missing host")
    port = port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise SSRFError("only ports 80 and 443 are allowed")
    try:
        addresses = resolver(host, port)
    except OSError as exc:
        raise SSRFError("host could not be resolved") from exc
    if not addresses:
        raise SSRFError("host could not be resolved")
    # Every resolved address must be public; one private answer rejects the host.
    for addr in addresses:
        if is_blocked_ip(addr):
            raise SSRFError("host resolves to a non-public address")
    return SafeTarget(url=url.strip(), scheme=parts.scheme, host=host, port=port, ip=addresses[0])
