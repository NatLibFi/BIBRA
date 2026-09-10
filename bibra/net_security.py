"""SSRF-hardened fetching of user-supplied URLs.

BIBRA's mitigation for the SSRF vector inherent in fetching a user-supplied
URL: a fetch policy (``UrlFetchPolicy``, loaded from ``BIBRA_URL_*`` env
vars), static URL validation (``validate_url``) re-applied on every
redirect hop, and ``fetch_file``, which permits egress only through a
configured proxy or explicit "direct" mode, checks resolved destination
IPs at connect time, and enforces size, timeout, and content (PDF) limits.

See the "Security" section of the README for the full model.
"""

import asyncio
import ipaddress
import logging
import os
import re
import socket
import urllib.parse
from dataclasses import dataclass

import httpx2

from bibra.env import parse_bool_env, parse_int_env, parse_list_env

logger = logging.getLogger(__name__)


# Sentinel value for BIBRA_URL_PROXY meaning "fetch directly, with the
# full in-app URL validation". Any other non-blank value is treated as a
# proxy URL; a blank/unset value means URL fetching is refused entirely.
URL_FETCH_DIRECT = "direct"

# Defaults for the URL fetch policy (BIBRA_URL_* env vars).
DEFAULT_URL_SCHEMES: list[str] = ["https"]
DEFAULT_URL_CONTENT_TYPES: list[str] = ["application/pdf"]
DEFAULT_URL_MAX_BYTES: int = 50 * 1024 * 1024  # 50 MiB
DEFAULT_URL_TIMEOUT: int = 30  # seconds
DEFAULT_URL_MAX_REDIRECTS: int = 5
DEFAULT_URL_ALLOW_IP_HOSTS: bool = False


@dataclass(frozen=True)
class UrlFetchPolicy:
    """Policy governing how BIBRA fetches user-supplied URLs (SSRF hardening).

    Attributes:
        proxy: The egress proxy URL, the literal sentinel "direct" (see
            URL_FETCH_DIRECT) for direct egress, or None to refuse fetching.
        schemes: Allowed URL schemes (e.g. ["https"]).
        content_types: Allowed response content types (MIME, no parameters).
        max_bytes: Hard cap on total downloaded bytes.
        timeout: Whole seconds for connect/read/write/pool timeouts.
        max_redirects: Maximum number of redirect hops; every hop is
            re-validated against the policy.
        allow_ip_hosts: Whether URLs whose host is an IP literal are allowed.
    """

    proxy: str | None
    schemes: tuple[str, ...]
    content_types: tuple[str, ...]
    max_bytes: int
    timeout: int
    max_redirects: int
    allow_ip_hosts: bool

    @property
    def proxy_required(self) -> bool:
        """True when URL fetching must be refused (no proxy or direct set)."""
        return self.proxy is None


def load_url_fetch_policy(cli_fallback: bool = False) -> UrlFetchPolicy:
    """Build a UrlFetchPolicy from the BIBRA_URL_* environment variables.

    Semantics of BIBRA_URL_PROXY (blank/whitespace normalized to unset):
      - unset: URL fetching is refused (``proxy_required`` is True), unless
        ``cli_fallback`` is set, in which case "direct" is used instead
      - "direct": direct egress is allowed, subject to full in-app validation
      - anything else: used as the egress proxy URL

    Invalid numeric/boolean values are logged and replaced by their
    defaults, so that a misconfigured setting never crashes the app.
    """
    proxy_raw = os.environ.get("BIBRA_URL_PROXY")
    proxy = proxy_raw.strip() if proxy_raw and proxy_raw.strip() else None
    if proxy is None and cli_fallback:
        proxy = URL_FETCH_DIRECT
    return UrlFetchPolicy(
        proxy=proxy,
        schemes=parse_list_env("BIBRA_URL_SCHEMES", DEFAULT_URL_SCHEMES),
        content_types=parse_list_env(
            "BIBRA_URL_CONTENT_TYPES", DEFAULT_URL_CONTENT_TYPES
        ),
        max_bytes=parse_int_env("BIBRA_URL_MAX_BYTES", DEFAULT_URL_MAX_BYTES),
        timeout=parse_int_env("BIBRA_URL_TIMEOUT", DEFAULT_URL_TIMEOUT),
        max_redirects=parse_int_env(
            "BIBRA_URL_MAX_REDIRECTS", DEFAULT_URL_MAX_REDIRECTS
        ),
        allow_ip_hosts=parse_bool_env(
            "BIBRA_URL_ALLOW_IP_HOSTS", DEFAULT_URL_ALLOW_IP_HOSTS
        ),
    )


#: Read the response body in chunks no larger than this while enforcing the
#: size cap, so we can abort mid-stream without buffering unbounded data.
_FETCH_CHUNK_SIZE = 65536

#: IPv4 ranges that must never be reachable through user-supplied URLs.
BLOCKED_IPV4_NETS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("0.0.0.0/8"),  # "this" network
    ipaddress.IPv4Network("10.0.0.0/8"),  # private
    ipaddress.IPv4Network("127.0.0.0/8"),  # loopback
    ipaddress.IPv4Network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.IPv4Network("172.16.0.0/12"),  # private
    ipaddress.IPv4Network("192.168.0.0/16"),  # private
    ipaddress.IPv4Network("100.64.0.0/10"),  # CGNAT
    ipaddress.IPv4Network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.IPv4Network("192.0.2.0/24"),  # documentation
    ipaddress.IPv4Network("198.18.0.0/15"),  # benchmarking
    ipaddress.IPv4Network("198.51.100.0/24"),  # documentation
    ipaddress.IPv4Network("203.0.113.0/24"),  # documentation
    ipaddress.IPv4Network("224.0.0.0/4"),  # multicast
    ipaddress.IPv4Network("240.0.0.0/4"),  # reserved
    ipaddress.IPv4Network("255.255.255.255/32"),  # broadcast
)

#: IPv6 ranges that must never be reachable through user-supplied URLs.
BLOCKED_IPV6_NETS: tuple[ipaddress.IPv6Network, ...] = (
    ipaddress.IPv6Network("::/128"),  # unspecified
    ipaddress.IPv6Network("::1/128"),  # loopback
    ipaddress.IPv6Network("::ffff:0:0/96"),  # IPv4-mapped
    ipaddress.IPv6Network("64:ff9b::/96"),  # NAT64
    ipaddress.IPv6Network("100::/64"),  # discard-only
    ipaddress.IPv6Network("fc00::/7"),  # unique local
    ipaddress.IPv6Network("fe80::/10"),  # link-local
    ipaddress.IPv6Network("ff00::/8"),  # multicast
)

# Hostnames consisting solely of digits are rejected as possible decimal
# IP obfuscation (e.g. "2130706433" == 127.0.0.1 on some resolvers).
_NUMERIC_HOST_RE = re.compile(r"^\d+$")


class UrlPolicyError(Exception):
    """Raised when a URL or downloaded content violates the fetch policy.

    The exception message is intentionally generic so that it can be
    shown to API clients without leaking internal details (hostnames,
    resolved IPs, redirect targets). Full context is logged by the
    raising code before re-raising or converting to a client error.
    """


class ProxyRequiredError(UrlPolicyError):
    """Raised when URL fetching is attempted while no proxy/direct is set.

    Distinguished from ``UrlPolicyError`` so callers can map it to a
    503 "service unavailable" (configuration issue) rather than a 400
    (client-supplied URL rejected).
    """

    MESSAGE = "URL fetching is disabled. Configure BIBRA_URL_PROXY to enable it."


def _normalize_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwrap IPv4-mapped IPv6 addresses (e.g. ::ffff:10.0.0.1)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_blocked_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True if the IP address is in a blocked (non-public) range.

    IPv4-mapped IPv6 addresses are unwrapped before checking so that
    e.g. ``::ffff:127.0.0.1`` is blocked just like ``127.0.0.1``.
    """
    ip = _normalize_ip(ip)
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in BLOCKED_IPV4_NETS)
    return any(ip in net for net in BLOCKED_IPV6_NETS)


def is_ip_literal(host: str) -> bool:
    """Return True if the hostname is (or looks like) an IP literal.

    Recognizes standard IPv4/IPv6 literals, bracketed IPv6 (the URL
    form), and all-numeric hostnames that some resolvers accept as
    decimal IPv4 obfuscation.
    """
    candidate = host.strip()
    if not candidate:
        return False
    # Bracketed IPv6 form, e.g. "[::1]"
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if _NUMERIC_HOST_RE.match(candidate):
        return True
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        return False


def parse_ip_host(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a hostname as an IP address, or return None if not parseable.

    Handles bracketed IPv6 and unwraps IPv4-mapped IPv6 addresses.
    """
    candidate = host.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return _normalize_ip(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def validate_url(url: str, policy: UrlFetchPolicy) -> None:
    """Statically validate a URL against the fetch policy.

    This is a pre-flight check performed before any network activity
    (and again on every redirect hop). It does not resolve hostnames;
    the connect-time check of resolved IPs is a separate layer.

    Args:
        url: The URL to validate.
        policy: The active UrlFetchPolicy.

    Raises:
        UrlPolicyError: If the URL violates any policy rule. The message
            is generic (no hostnames or internal details) so it is safe
            to surface to clients.
    """
    if policy.proxy_required:
        logger.warning("URL fetch refused (no proxy configured): %s", url)
        raise ProxyRequiredError(ProxyRequiredError.MESSAGE)

    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        # Accessing .port raises ValueError for non-numeric or
        # out-of-range ports; treat those as malformed URLs.
        # The value itself is unused, so discard it into a throwaway name.
        _ = parts.port
    except ValueError:
        logger.warning("Malformed URL rejected: %r", url)
        raise UrlPolicyError("URL rejected by fetch policy") from None

    scheme = (parts.scheme or "").lower()
    if scheme not in policy.schemes:
        logger.warning(
            "URL scheme %r rejected (allowed: %s): %s",
            scheme,
            ",".join(policy.schemes),
            url,
        )
        raise UrlPolicyError("URL rejected by fetch policy")

    if not host:
        logger.warning("URL without host rejected: %s", url)
        raise UrlPolicyError("URL rejected by fetch policy")

    if is_ip_literal(host):
        ip = parse_ip_host(host)
        if ip is None:
            # All-numeric hostname (decimal IP obfuscation attempt); always
            # rejected, even when IP literal hosts are otherwise allowed.
            logger.warning("Numeric hostname rejected: %s", url)
            raise UrlPolicyError("URL rejected by fetch policy")
        if is_blocked_ip(ip):
            logger.warning("Blocked IP literal rejected: %s", url)
            raise UrlPolicyError("URL rejected by fetch policy")
        if not policy.allow_ip_hosts:
            logger.warning("IP literal host rejected: %s", url)
            raise UrlPolicyError("URL rejected by fetch policy")


def is_pdf(data: bytes) -> bool:
    """Return True if the byte string looks like a PDF file.

    Searches for the ``%PDF`` magic signature within the first 1024
    bytes, which matches PDF reader behaviour: some producers emit
    a preamble (whitespace, a UTF-8 BOM, or other junk) before the
    header, and spec-compliant readers locate the header within the
    first 1024 bytes of the file.
    """
    return b"%PDF" in data[:1024]


class DownloadSizeExceededError(UrlPolicyError):
    """Raised when a download exceeds the policy's ``max_bytes`` cap."""

    MESSAGE = "Download rejected by fetch policy"


class _BlockedDestinationError(Exception):
    """Internal: a resolved destination IP is blocked by policy.

    Not a ``UrlPolicyError`` on purpose — it is raised inside a transport
    hook and translated there; callers never see it directly.
    """

    def __init__(self, url: str, ip: str):
        super().__init__(f"blocked destination {ip} for {url}")
        self.url = url
        self.ip = ip


class _DnsResolutionError(Exception):
    """Internal: a hostname could not be resolved locally.

    Not a policy violation — the host simply does not resolve (typo,
    offline). Translated to a connection error (502 at the API level)
    rather than a fetch-policy rejection (400).
    """

    def __init__(self, url: str):
        super().__init__(f"could not resolve host for {url}")
        self.url = url


async def _check_destination(host: str, port: int | None) -> None:
    """Raise _BlockedDestinationError or _DnsResolutionError on failure.

    Resolves the hostname on the running event loop (non-blocking) and
    checks every address a connection could hit, which enforces the
    blocked-IP policy at connect time and mitigates DNS rebinding.
    IP literals are checked directly without a DNS lookup.

    Raises:
        _BlockedDestinationError: If any resolved IP is blocked.
        _DnsResolutionError: If the hostname does not resolve at all.
    """
    literal = parse_ip_host(host)
    if literal is not None:
        if is_blocked_ip(literal):
            raise _BlockedDestinationError(f"http://{host}", str(literal))
        return

    if port is None:
        port = 443
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as e:
        logger.warning("DNS resolution failed for %s: %s", host, e)
        raise _DnsResolutionError(f"http://{host}") from None
    seen: set[str] = set()
    for info in infos:
        ip_str = info[4][0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        ip = _normalize_ip(ipaddress.ip_address(ip_str))
        if is_blocked_ip(ip):
            raise _BlockedDestinationError(f"http://{host}", str(ip))


def _build_async_transport(
    policy: UrlFetchPolicy, proxy: str | None
) -> httpx2.AsyncHTTPTransport:
    """Build an async transport that re-validates every request URL against
    the policy (each redirect hop issues a fresh request through the
    transport, so every hop is checked) and, in direct mode, additionally
    checks the resolved destination IP at connect time to close the
    DNS-rebinding window (in proxy mode the proxy's egress allowlist is
    authoritative, and local DNS results may not match its resolver).
    ``trust_env=False`` ignores ambient HTTP(S)_PROXY/NO_PROXY vars: the
    only egress route ever in effect is the explicit policy proxy.
    """
    proxy_arg = httpx2.Proxy(proxy) if proxy else None

    class _SafeAsyncTransport(httpx2.AsyncHTTPTransport):
        async def handle_async_request(self, request: httpx2.Request):
            validate_url(str(request.url), policy)
            if proxy is None:
                # Direct egress: check the resolved destination IP
                # (closes the DNS-rebinding window). In proxy mode the
                # proxy's egress allowlist is the authoritative control.
                await _check_destination(request.url.host, request.url.port)
            return await super().handle_async_request(request)

    return _SafeAsyncTransport(proxy=proxy_arg, trust_env=False)


def _validate_response_headers(
    response: httpx2.Response, policy: UrlFetchPolicy
) -> None:
    """Check the response Content-Type against the policy allowlist."""
    raw = response.headers.get("content-type", "")
    media_type = raw.split(";", 1)[0].strip().lower()
    if media_type not in policy.content_types:
        logger.warning(
            "Content-Type %r rejected (allowed: %s)",
            media_type,
            ",".join(policy.content_types),
        )
        raise UrlPolicyError("URL rejected by fetch policy")


async def fetch_file(url: str, policy: UrlFetchPolicy) -> bytes:
    """Download a user-supplied PDF with SSRF protection (async).

    Applies, in order: static URL validation (re-applied on every redirect
    hop by the transport), connect-time resolved-IP blocking in direct
    mode, a hard byte cap, explicit timeouts, and a Content-Type allowlist
    plus magic-byte verification.

    Raises:
        ProxyRequiredError: If no proxy/direct egress is configured.
        DownloadSizeExceededError: If the body exceeds ``policy.max_bytes``.
        UrlPolicyError: If any other policy rule is violated.
        httpx2.HTTPError: If the network request itself fails.
    """
    validate_url(url, policy)
    proxy = policy.proxy if policy.proxy not in (None, URL_FETCH_DIRECT) else None

    try:
        async with (
            httpx2.AsyncClient(
                timeout=httpx2.Timeout(policy.timeout),
                follow_redirects=True,
                max_redirects=policy.max_redirects,
                transport=_build_async_transport(policy, proxy),
            ) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code >= 400:
                logger.warning("HTTP %d fetching %s", response.status_code, url)
                raise httpx2.HTTPError(f"HTTP {response.status_code} while downloading")
            _validate_response_headers(response, policy)

            # Pre-check Content-Length when present.
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > policy.max_bytes:
                        raise DownloadSizeExceededError(
                            DownloadSizeExceededError.MESSAGE
                        )
                except ValueError:
                    logger.debug(
                        "Non-numeric Content-Length %r from %s",
                        content_length,
                        url,
                    )

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes(chunk_size=_FETCH_CHUNK_SIZE):
                total += len(chunk)
                if total > policy.max_bytes:
                    logger.warning(
                        "Download from %s exceeded %d bytes; aborting",
                        url,
                        policy.max_bytes,
                    )
                    raise DownloadSizeExceededError(DownloadSizeExceededError.MESSAGE)
                chunks.append(chunk)
            data = b"".join(chunks)
    except _BlockedDestinationError as e:
        logger.warning("Blocked destination during fetch: %s", e)
        raise UrlPolicyError("URL rejected by fetch policy") from None
    except _DnsResolutionError as e:
        logger.warning("Host resolution failed during fetch: %s", e)
        raise httpx2.ConnectError("Could not resolve host") from None

    if not is_pdf(data):
        logger.warning("Downloaded content failed magic-byte validation")
        raise UrlPolicyError("URL rejected by fetch policy")
    return data
