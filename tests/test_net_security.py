"""Tests for the SSRF validation layer in bibra/net_security.py.

These are pure unit tests: no network I/O is performed. The fetch layer
that builds on top of this module is tested in a later step.
"""

import ipaddress

import pytest

from bibra.net_security import (
    ProxyRequiredError,
    UrlFetchPolicy,
    UrlPolicyError,
    is_blocked_ip,
    is_ip_literal,
    is_pdf,
    load_url_fetch_policy,
    parse_ip_host,
    redact_url,
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
        """With no proxy configured, every URL is refused.

        ProxyRequiredError is a UrlPolicyError but carries its own type and
        a message that names the env var to fix.
        """
        policy = make_policy(proxy=None)

        with pytest.raises(ProxyRequiredError) as exc_info:
            validate_url("https://example.com/paper.pdf", policy)

        assert isinstance(exc_info.value, UrlPolicyError)
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

    def test_numeric_hostname_rejected_even_when_ip_hosts_allowed(self):
        """Numeric hostnames stay rejected even with allow_ip_hosts=True."""
        policy = make_policy(allow_ip_hosts=True)

        with pytest.raises(UrlPolicyError):
            validate_url("https://2130706433/paper.pdf", policy)

    def test_unparseable_numeric_hostname_rejected(self):
        """A numeric hostname that is not a valid IPv4 literal is rejected.

        4294967296 == 2**32 is just above the IPv4 address space, so
        ipaddress.ip_address() cannot parse it; the is_ip_literal gate
        still classifies it as an IP literal and rejects it.
        """
        policy = make_policy()

        with pytest.raises(UrlPolicyError):
            validate_url("https://4294967296/paper.pdf", policy)

    def test_error_messages_are_generic(self):
        """Rejection messages never leak the offending URL."""
        policy = make_policy()

        with pytest.raises(UrlPolicyError) as exc_info:
            validate_url("http://example.com/secret.pdf", policy)

        assert "example.com" not in str(exc_info.value)
        assert "secret.pdf" not in str(exc_info.value)


class TestRedactUrl:
    """Tests for redact_url (log-safe URL representation)."""

    def test_userinfo_stripped_with_marker(self):
        """Credentials in the userinfo component are removed."""
        url = "https://user:ghp_abc123@api.example.com/reports/q1.pdf"
        assert redact_url(url) == (
            "https://api.example.com/reports/q1.pdf [userinfo/query/fragment redacted]"
        )
        assert "ghp_abc123" not in redact_url(url)

    def test_query_stripped_with_marker(self):
        """Tokens in the query string are removed."""
        url = "https://api.example.com/doc.pdf?api_key=sk_live_9988"
        assert redact_url(url) == (
            "https://api.example.com/doc.pdf [userinfo/query/fragment redacted]"
        )
        assert "sk_live_9988" not in redact_url(url)

    def test_fragment_stripped_with_marker(self):
        """Fragments are removed as well."""
        url = "https://example.com/doc.pdf#access=token123"
        assert redact_url(url) == (
            "https://example.com/doc.pdf [userinfo/query/fragment redacted]"
        )
        assert "token123" not in redact_url(url)

    def test_port_and_path_preserved(self):
        """Host, port, and path survive redaction for diagnosability."""
        url = "https://cdn.files.example.net:8080/pdfs/98765/paper.pdf?signature=HMAC"
        assert redact_url(url) == (
            "https://cdn.files.example.net:8080/pdfs/98765/paper.pdf"
            " [userinfo/query/fragment redacted]"
        )

    def test_clean_url_returned_unchanged(self):
        """A URL with no userinfo/query/fragment is byte-identical."""
        url = "https://example.com:443/doc.pdf"
        assert redact_url(url) == url

    def test_clean_url_no_marker(self):
        """No redaction marker is added when nothing was stripped."""
        assert "redacted" not in redact_url("https://example.com/doc.pdf")

    def test_unparseable_input_returned_unchanged(self):
        """Input that urlsplit cannot parse is returned as-is."""
        url = "not a url at all"
        assert redact_url(url) == url


class TestValidateUrlLogsRedacted:
    """Regression tests: rejection diagnostics must not persist secrets.

    URLs may carry credentials in userinfo/query strings; every log
    record emitted on a rejection path must be free of them.
    """

    SENSITIVE_URL = "https://user:supersecrettoken@api.example.com/doc.pdf?key=abc123"

    @staticmethod
    def _assert_logs_redacted(caplog, host):
        """No secret substrings in the logs; the host is still diagnosable."""
        assert "supersecrettoken" not in caplog.text
        assert "key=abc123" not in caplog.text
        assert host in caplog.text

    def test_scheme_rejection_logs_redacted(self, caplog):
        """A scheme rejection never logs userinfo or query verbatim."""
        policy = make_policy()

        with caplog.at_level("WARNING"), pytest.raises(UrlPolicyError):
            validate_url("http://" + self.SENSITIVE_URL.split("://", 1)[1], policy)

        self._assert_logs_redacted(caplog, "api.example.com/doc.pdf")

    def test_blocked_ip_rejection_logs_redacted(self, caplog):
        """A blocked-IP rejection never logs userinfo or query verbatim."""
        policy = make_policy()
        url = "https://user:supersecrettoken@169.254.169.254/meta?key=abc123"

        with caplog.at_level("WARNING"), pytest.raises(UrlPolicyError):
            validate_url(url, policy)

        self._assert_logs_redacted(caplog, "169.254.169.254")

    def test_proxy_required_rejection_logs_redacted(self, caplog):
        """The 503 no-proxy path never logs userinfo or query verbatim."""
        policy = make_policy(proxy=None)

        with caplog.at_level("WARNING"), pytest.raises(ProxyRequiredError):
            validate_url(self.SENSITIVE_URL, policy)

        self._assert_logs_redacted(caplog, "api.example.com/doc.pdf")


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
        ["label", "data"],
        [
            ["zip", b"PK\x03\x04"],
            ["png", b"\x89PNG\r\n\x1a\n"],
            ["html", b"<html>not a pdf</html>"],
            ["empty", b""],
            ["null_bytes", b"\x00" * 2048],
        ],
        ids=["zip", "png", "html", "empty", "null_bytes"],
    )
    def test_non_pdf_rejected(self, label: str, data: bytes):
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
