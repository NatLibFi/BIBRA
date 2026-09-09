"""Network security helpers for fetching user-supplied URLs.

This module implements BIBRA's SSRF mitigation: a validation layer and a
hardened fetch function.

Validation components:
    - ``UrlPolicyError``: raised when a URL or downloaded content violates
      the fetch policy. Carries a safe, generic message suitable for
      client-facing error responses; full details are logged server-side.
    - ``is_blocked_ip``: range-table check that refuses private, loopback,
      link-local (cloud metadata), CGNAT, and other non-public addresses.
    - ``validate_url``: static validation of a URL against the policy
      (scheme allowlist, host presence, IP-literal rejection).
    - ``ContentValidator`` / ``is_pdf``: pluggable byte-level content
      checks (magic bytes). Currently PDFs are the only supported type;
      future file types add their own validators.

Fetch components:
    - ``fetch_file`` / ``fetch_file_sync``: download a user-supplied URL
      with defense in depth: static URL validation, connect-time resolved-IP
      checking (closes DNS-rebinding and covers every redirect hop), a hard
      size cap, explicit timeouts, and content-type plus magic-byte
      verification. Egress is only permitted through a configured proxy or in
      explicit "direct" mode.
"""

import asyncio
import ipaddress
import logging
import re
import socket
import urllib.parse
from typing import Protocol

import httpx2

from bibra.config import URL_FETCH_DIRECT, UrlFetchPolicy

logger = logging.getLogger(__name__)

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


class ContentValidator(Protocol):
    """A byte-level check that a downloaded file is of an expected type."""

    def __call__(self, data: bytes) -> bool:
        """Return True if data matches the expected content type."""
        ...


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
        _port = parts.port
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

    ip = parse_ip_host(host)
    if ip is not None:
        if is_blocked_ip(ip):
            logger.warning("Blocked IP literal rejected: %s", url)
            raise UrlPolicyError("URL rejected by fetch policy")
        if not policy.allow_ip_hosts:
            logger.warning("IP literal host rejected: %s", url)
            raise UrlPolicyError("URL rejected by fetch policy")
    elif _NUMERIC_HOST_RE.match(host):
        # All-numeric hostname (decimal IP obfuscation attempt).
        logger.warning("Numeric hostname rejected: %s", url)
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


async def _check_destination(host: str, port: int | None) -> None:
    """Raise _BlockedDestinationError if any resolved IP is blocked.

    Resolves the hostname on the running event loop (non-blocking) and
    checks every address a connection could hit, which enforces the
    blocked-IP policy at connect time and mitigates DNS rebinding.
    IP literals are checked directly without a DNS lookup.
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
        raise _BlockedDestinationError(f"http://{host}", "unresolvable") from None
    seen: set[str] = set()
    for info in infos:
        ip_str = info[4][0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        ip = _normalize_ip(ipaddress.ip_address(ip_str))
        if is_blocked_ip(ip):
            raise _BlockedDestinationError(f"http://{host}", str(ip))


def _build_async_transport(proxy: str | None) -> httpx2.AsyncHTTPTransport:
    """Build an async transport that validates each request's destination.

    Every request URL's resolved IP is re-checked at connect time, which
    closes the DNS-rebinding window and covers every redirect hop
    (httpx issues a fresh request through the transport for each hop).

    Args:
        proxy: Proxy URL to route through, or None for direct egress.
    """
    proxy_arg = httpx2.Proxy(proxy) if proxy else None

    class _SafeAsyncTransport(httpx2.AsyncHTTPTransport):
        async def handle_async_request(self, request: httpx2.Request):
            await _check_destination(request.url.host, request.url.port)
            return await super().handle_async_request(request)

    return _SafeAsyncTransport(proxy=proxy_arg)


def _client_kwargs(policy: UrlFetchPolicy) -> dict:
    """Build httpx2 AsyncClient kwargs from the policy.

    The ``transport`` kwarg carries the destination-validating transport;
    no ``proxy`` kwarg is used so that the client does not also mount its
    own proxy transport (the proxy, when configured, lives inside our
    transport).
    """
    timeout = httpx2.Timeout(policy.timeout)
    proxy: str | None = None
    if policy.proxy is not None and policy.proxy != URL_FETCH_DIRECT:
        proxy = policy.proxy

    return {
        "timeout": timeout,
        "follow_redirects": True,
        "max_redirects": policy.max_redirects,
        "transport": _build_async_transport(proxy),
    }


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


def _validate_content(
    data: bytes, expected_types: tuple[ContentValidator, ...]
) -> None:
    """Verify the downloaded bytes pass at least one content validator."""
    if not any(v(data) for v in expected_types):
        logger.warning("Downloaded content failed magic-byte validation")
        raise UrlPolicyError("URL rejected by fetch policy")


async def fetch_file(
    url: str,
    policy: UrlFetchPolicy,
    *,
    expected_types: tuple[ContentValidator, ...] = (is_pdf,),
) -> bytes:
    """Download a user-supplied URL with SSRF protection (async).

    Layers of defense, in order:
      1. ``validate_url`` (static: proxy mode, scheme, host, IP literal)
      2. httpx2 request through a wrapped transport that re-validates the
         resolved destination IP at connect time for every redirect hop
      3. hard ``max_bytes`` cap, enforced against Content-Length and by
         counting streamed bytes
      4. explicit timeouts (``policy.timeout``)
      5. Content-Type allowlist + at-least-one magic-byte validator

    Args:
        url: The URL to fetch.
        policy: The active UrlFetchPolicy.
        expected_types: Content validators; the body must pass at least one.

    Returns:
        The downloaded bytes.

    Raises:
        ProxyRequiredError: If no proxy/direct egress is configured.
        DownloadSizeExceededError: If the body exceeds ``policy.max_bytes``.
        UrlPolicyError: If any other policy rule is violated.
        httpx2.HTTPError: If the network request itself fails.
    """
    validate_url(url, policy)

    kwargs = _client_kwargs(policy)

    try:
        async with (
            httpx2.AsyncClient(**kwargs) as client,
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

    _validate_content(data, expected_types)
    return data


def fetch_file_sync(
    url: str,
    policy: UrlFetchPolicy,
    *,
    expected_types: tuple[ContentValidator, ...] = (is_pdf,),
) -> bytes:
    """Synchronous wrapper around :func:`fetch_file` for the CLI.

    Runs the async fetch on a fresh event loop. Safe to call from a
    synchronous (non-loop) context such as the Click CLI.
    """

    async def _run() -> bytes:
        return await fetch_file(url, policy, expected_types=expected_types)

    return asyncio.run(_run())
