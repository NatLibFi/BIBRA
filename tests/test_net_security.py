"""Tests for the SSRF validation layer in bibra/net_security.py.

These are pure unit tests: no network I/O is performed. The fetch layer
that builds on top of this module is tested in a later step.
"""

import ipaddress

import pytest

from bibra.config import UrlFetchPolicy, load_url_fetch_policy
from bibra.net_security import (
    ContentValidator,
    ProxyRequiredError,
    UrlPolicyError,
    is_blocked_ip,
    is_ip_literal,
    is_pdf,
    parse_ip_host,
    validate_url,
)


def make_policy(**overrides) -> UrlFetchPolicy:
    """Build a UrlFetchPolicy with sensible test defaults.

    The default test policy allows direct egress ("direct") over https
    so that individual rules can be tested in isolation.
    """
    defaults = {
        "proxy": "direct",
        "schemes": ("https",),
        "content_types": ("application/pdf",),
        "max_bytes": 1024,
        "timeout": 5.0,
        "max_redirects": 3,
        "allow_ip_hosts": False,
    }
    defaults.update(overrides)
    return UrlFetchPolicy(**defaults)


class TestIsBlockedIp:
    """Tests for the blocked-IP range tables."""

    @pytest.mark.parametrize(
        ("address",),
        [
            ("0.0.0.0",),
            ("10.0.0.1",),
            ("10.255.255.255",),
            ("127.0.0.1",),
            ("127.255.0.1",),
            ("169.254.169.254",),  # cloud metadata
            ("172.16.0.1",),
            ("172.31.255.255",),
            ("192.168.1.1",),
            ("100.64.0.1",),
            ("100.127.255.255",),
            ("192.0.0.8",),
            ("192.0.2.44",),
            ("198.18.0.1",),
            ("198.51.100.23",),
            ("203.0.113.7",),
            ("224.0.0.1",),
            ("239.255.255.255",),
            ("240.0.0.1",),
            ("254.255.255.255",),
            ("255.255.255.255",),
        ],
    )
    def test_blocked_ipv4(self, address: str):
        """Every documented private/reserved IPv4 range is blocked."""
        assert is_blocked_ip(ipaddress.IPv4Address(address)) is True

    @pytest.mark.parametrize(
        ("address",),
        [
            ("::",),
            ("::1",),
            ("::ffff:127.0.0.1",),  # IPv4-mapped loopback
            ("::ffff:10.0.0.1",),  # IPv4-mapped private
            ("::ffff:169.254.169.254",),  # IPv4-mapped metadata
            ("64:ff9b::1",),
            ("100::1",),
            ("fc00::1",),
            ("fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff",),
            ("fe80::1",),
            ("ff02::1",),
            ("ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff",),
        ],
    )
    def test_blocked_ipv6(self, address: str):
        """Every documented private/reserved IPv6 range is blocked."""
        assert is_blocked_ip(ipaddress.IPv6Address(address)) is True

    @pytest.mark.parametrize(
        ("address",),
        [
            ("8.8.8.8",),
            ("1.1.1.1",),
            ("93.184.216.34",),
            ("172.32.0.1",),  # just outside 172.16/12
            ("100.128.0.1",),  # just outside CGNAT
            ("223.255.255.255",),  # just below multicast
            ("2a00:1450::1",),
            ("2606:4700:4700::1111",),
        ],
    )
    def test_public_addresses_allowed(self, address: str):
        """Public addresses are not blocked."""
        assert is_blocked_ip(ipaddress.ip_address(address)) is False


class TestIsIpLiteral:
    """Tests for IP-literal hostname detection."""

    @pytest.mark.parametrize(
        ("host",),
        [
            ("127.0.0.1",),
            ("8.8.8.8",),
            ("::1",),
            ("2001:db8::1",),
            ("[::1]",),
            ("[2001:db8::1]",),
            ("2130706433",),  # all-numeric (decimal IP obfuscation)
            ("1234",),
        ],
    )
    def test_literals_detected(self, host: str):
        """Standard and obfuscated IP literals are detected."""
        assert is_ip_literal(host) is True

    @pytest.mark.parametrize(
        ["host"],
        [
            ["example.com"],
            ["sub.domain.example.org"],
            ["localhost"],
            ["123abc"],
            [""],
            ["   "],
        ],
    )
    def test_non_literals(self, host: str):
        """Ordinary hostnames are not IP literals."""
        assert is_ip_literal(host) is False


class TestParseIpHost:
    """Tests for parse_ip_host."""

    def test_ipv4(self):
        """A plain IPv4 host parses to an IPv4Address."""
        assert parse_ip_host("127.0.0.1") == ipaddress.IPv4Address("127.0.0.1")

    def test_bracketed_ipv6(self):
        """Bracketed IPv6 (URL form) is unwrapped."""
        assert parse_ip_host("[::1]") == ipaddress.IPv6Address("::1")

    def test_ipv4_mapped_ipv6_is_unwrapped(self):
        """IPv4-mapped IPv6 addresses normalize to their IPv4 form."""
        assert parse_ip_host("::ffff:10.0.0.1") == ipaddress.IPv4Address("10.0.0.1")

    def test_non_ip_returns_none(self):
        """Non-IP hostnames return None."""
        assert parse_ip_host("example.com") is None


class TestValidateUrl:
    """Tests for validate_url (static, pre-flight URL validation)."""

    def test_refused_when_proxy_not_configured(self):
        """With no proxy configured, every URL is refused."""
        policy = make_policy(proxy=None)

        with pytest.raises(ProxyRequiredError):
            validate_url("https://example.com/paper.pdf", policy)

    def test_proxy_required_is_distinguishable(self):
        """ProxyRequiredError is a UrlPolicyError but carries its own type."""
        policy = make_policy(proxy=None)

        with pytest.raises(UrlPolicyError) as exc_info:
            validate_url("https://example.com/paper.pdf", policy)

        assert isinstance(exc_info.value, ProxyRequiredError)
        assert "BIBRA_URL_PROXY" in str(exc_info.value)

    def test_https_url_accepted(self):
        """A well-formed https URL with a hostname passes."""
        policy = make_policy()

        assert validate_url("https://example.com/paper.pdf", policy) is None

    def test_scheme_not_allowed(self):
        """Schemes outside the allowlist are rejected."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError, match="fetch policy"):
            validate_url("http://example.com/paper.pdf", policy)

    def test_scheme_allowlist_extended(self):
        """Adding http to the allowlist permits it."""
        policy = make_policy(schemes=("https", "http"))

        assert validate_url("http://example.com/paper.pdf", policy) is None

    def test_scheme_is_case_insensitive(self):
        """Scheme matching is case-insensitive."""
        policy = make_policy()

        assert validate_url("HTTPS://example.com/paper.pdf", policy) is None

    def test_url_without_host_rejected(self):
        """A URL with no hostname is rejected."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError):
            validate_url("https:///paper.pdf", policy)

    def test_malformed_url_rejected(self):
        """An unparseable URL is rejected (no exception leaks)."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError):
            validate_url("https://example.com:badport/x", policy)

    @pytest.mark.parametrize(
        ("url",),
        [
            ("https://127.0.0.1/paper.pdf",),
            ("https://169.254.169.254/latest/meta-data/",),
            ("https://10.0.0.5/internal",),
            ("https://192.168.1.1/router",),
            ("https://[::1]/paper.pdf",),
            ("https://[::ffff:127.0.0.1]/paper.pdf",),
        ],
    )
    def test_blocked_ip_literals_rejected(self, url: str):
        """IP literals in blocked ranges are always rejected."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError):
            validate_url(url, policy)

    def test_public_ip_literal_rejected_by_default(self):
        """Even public IP literals are rejected unless explicitly allowed."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError):
            validate_url("https://93.184.216.34/paper.pdf", policy)

    def test_public_ip_literal_allowed_when_configured(self):
        """BIBRA_URL_ALLOW_IP_HOSTS semantics: public literals then pass."""
        policy = make_policy(allow_ip_hosts=True)

        assert validate_url("https://93.184.216.34/paper.pdf", policy) is None

    def test_numeric_hostname_rejected(self):
        """All-numeric hostnames (decimal IP obfuscation) are rejected."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError):
            validate_url("https://2130706433/paper.pdf", policy)

    def test_error_messages_are_generic(self):
        """Rejection messages never leak the offending URL."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError) as exc_info:
            validate_url("http://example.com/secret.pdf", policy)

        assert "example.com" not in str(exc_info.value)
        assert "secret.pdf" not in str(exc_info.value)


class TestIsPdf:
    """Tests for the PDF content validator."""

    def test_valid_pdf_header(self):
        """A standard PDF header is recognized."""
        assert is_pdf(b"%PDF-1.7\n%blah\n...") is True

    def test_pdf_with_leading_whitespace(self):
        """Leading whitespace before the magic bytes is tolerated."""
        assert is_pdf(b"  \t\r\n%PDF-1.4\n") is True

    def test_pdf_with_utf8_bom(self):
        """A UTF-8 BOM before the magic bytes is tolerated."""
        assert is_pdf(b"\xef\xbb\xbf%PDF-1.5\n") is True

    @pytest.mark.parametrize(
        ["data"],
        [
            [b"PK\x03\x04"],  # zip
            [b"\x89PNG\r\n\x1a\n"],  # png
            [b"<html>not a pdf</html>"],
            [b""],
            [b"\x00" * 2048],
        ],
    )
    def test_non_pdf_rejected(self, data: bytes):
        """Non-PDF content is rejected."""
        assert is_pdf(data) is False

    def test_magic_bytes_beyond_search_window(self):
        """%PDF beyond the 1024-byte search window is not recognized."""
        data = b"x" * 1024 + b"%PDF-1.7"

        assert is_pdf(data) is False

    def test_magic_bytes_within_search_window(self):
        """%PDF fully within the 1024-byte window is recognized."""
        data = b"x" * 1010 + b"%PDF-1.7"

        assert is_pdf(data) is True


class TestContentValidatorProtocol:
    """Tests that validators plug into the ContentValidator protocol."""

    def test_is_pdf_satisfies_protocol(self):
        """is_pdf is structurally compatible with ContentValidator."""
        validator: ContentValidator = is_pdf

        assert validator(b"%PDF-1.7") is True

    def test_custom_validator(self):
        """A custom validator (e.g. for a future file type) can be passed."""

        def is_png(data: bytes) -> bool:
            return data.startswith(b"\x89PNG")

        validator: ContentValidator = is_png

        assert validator(b"\x89PNG\r\n\x1a\n") is True
        assert validator(b"%PDF-1.7") is False


class TestPolicyIntegration:
    """End-to-end tests combining load_url_fetch_policy with validate_url."""

    def test_default_policy_refuses_fetches(self, monkeypatch):
        """With no env vars set, validation refuses everything (503 case)."""
        for var in (
            "BIBRA_URL_PROXY",
            "BIBRA_URL_SCHEMES",
            "BIBRA_URL_CONTENT_TYPES",
            "BIBRA_URL_MAX_BYTES",
            "BIBRA_URL_TIMEOUT",
            "BIBRA_URL_MAX_REDIRECTS",
            "BIBRA_URL_ALLOW_IP_HOSTS",
        ):
            monkeypatch.delenv(var, raising=False)

        policy = load_url_fetch_policy()

        with pytest.raises(ProxyRequiredError):
            validate_url("https://example.com/paper.pdf", policy)

    def test_direct_mode_allows_public_hostname(self, monkeypatch):
        """BIBRA_URL_PROXY=direct enables fetches of public https hosts."""
        monkeypatch.setenv("BIBRA_URL_PROXY", "direct")

        policy = load_url_fetch_policy()

        assert validate_url("https://example.com/paper.pdf", policy) is None

    def test_proxy_url_mode_allows_public_hostname(self, monkeypatch):
        """A configured proxy URL enables fetches of public https hosts."""
        monkeypatch.setenv("BIBRA_URL_PROXY", "http://proxy.example.com:8080")

        policy = load_url_fetch_policy()

        assert validate_url("https://example.com/paper.pdf", policy) is None
