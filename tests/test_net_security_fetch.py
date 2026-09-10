"""Integration tests for the fetch layer in bibra/net_security.py.

These tests spin up real HTTP servers bound to 127.0.0.1 to prove the SSRF
mitigations end-to-end:

    - connect-time resolved-IP blocking (loopback literals and the
      localhost hostname are refused without any patching)
    - redirect-hijack refusal (a reachable host 302-redirecting to the
      cloud-metadata address is refused on the hop)
    - per-hop policy re-application (redirects to a disallowed scheme or
      to an IP literal with allow_ip_hosts=False are refused on the hop)
    - hard size-cap enforcement (Content-Length pre-check and mid-stream)
    - content-type allowlist and magic-byte verification
    - proxy-required refusal

Because the loopback range is blocked by design, tests that need a
*successful* fetch from the local test server monkeypatch
``net_security.is_blocked_ip`` to allow the connection. Tests that assert
blocking use the real, unpatched check.
"""

import asyncio
import http.server
import socket
import socketserver
import threading

import httpx2
import pytest

import bibra.net_security as ns

PDF_BODY = b"%PDF-1.7\n% fake pdf content\n%%EOF\n"
METADATA_IP = "169.254.169.254"


def _make_policy(**overrides) -> ns.UrlFetchPolicy:
    """Build a policy that allows http to localhost for these tests."""
    defaults = {
        "proxy": "direct",
        "schemes": ("http",),
        "content_types": ("application/pdf",),
        "max_bytes": 1024 * 1024,
        "timeout": 5.0,
        "max_redirects": 3,
        "allow_ip_hosts": True,
    }
    defaults.update(overrides)
    return ns.UrlFetchPolicy(**defaults)


class _Handler(http.server.BaseHTTPRequestHandler):
    """Base handler; subclasses override do_GET."""

    def log_message(self, *args):
        pass

    def _send(self, body: bytes, content_type: str = "application/pdf"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _RedirectHandler(_Handler):
    """302-redirect every request to a class-level Location."""

    location: str = ""

    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", self.location)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _start_server(handler_cls) -> tuple[socketserver.TCPServer, int]:
    """Start a TCPServer on 127.0.0.1 with a free port; return (srv, port)."""
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _start_recording_proxy() -> tuple[socket.socket, int, list]:
    """A socket that accepts (and closes) connections, recording them.

    Acts as a dummy forward proxy for tests: any connection made to it is
    evidence that egress was routed through it.
    """
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = sock.getsockname()[1]
    connections: list = []

    def _accept_loop():
        while True:
            try:
                conn, addr = sock.accept()
            except OSError:
                return
            connections.append(addr)
            conn.close()

    threading.Thread(target=_accept_loop, daemon=True).start()
    return sock, port, connections


@pytest.fixture
def pdf_server():
    """A local server that serves a valid PDF body."""

    class Handler(_Handler):
        def do_GET(self):
            self._send(PDF_BODY)

    srv, port = _start_server(Handler)
    yield port
    srv.shutdown()
    srv.server_close()


class TestDnsFailure:
    """A hostname that does not resolve is a download failure, not a
    policy rejection (no UrlPolicyError)."""

    def test_unresolvable_host_raises_connect_error(self, monkeypatch):
        """socket.gaierror surfaces as httpx2.ConnectError (a httpx2.HTTPError)."""
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("name not resolved")),
        )

        # ConnectError is the specific type; it is also an httpx2.HTTPError
        # (so the API's 502 handler catches it) and NOT a UrlPolicyError.
        with pytest.raises(httpx2.ConnectError) as exc_info:
            asyncio.run(
                ns.fetch_file("http://nonexistent-host.invalid/x.pdf", _make_policy())
            )

        assert isinstance(exc_info.value, httpx2.HTTPError)
        assert not isinstance(exc_info.value, ns.UrlPolicyError)
        # No internal details (hostname) leak into the client-facing message.
        assert "nonexistent-host.invalid" not in str(exc_info.value)


class TestConnectTimeBlocking:
    """The resolved destination IP must be blocked at connect time."""

    def test_ip_literal_loopback_refused(self, pdf_server):
        """A loopback IP literal is refused (real, unpatched check)."""
        policy = _make_policy()

        with pytest.raises(ns.UrlPolicyError):
            asyncio.run(ns.fetch_file(f"http://127.0.0.1:{pdf_server}/x.pdf", policy))

    def test_localhost_hostname_refused(self, pdf_server):
        """http://localhost resolves to loopback and is refused.

        Exercises the async DNS-resolution path (loop.getaddrinfo) with a
        real hostname, no patching.
        """
        policy = _make_policy(allow_ip_hosts=False)

        with pytest.raises(ns.UrlPolicyError):
            asyncio.run(ns.fetch_file(f"http://localhost:{pdf_server}/x.pdf", policy))

    def test_metadata_ip_literal_refused(self, pdf_server):
        """The cloud-metadata IP is refused even in proxy-required bypass."""
        policy = _make_policy()

        with pytest.raises(ns.UrlPolicyError):
            asyncio.run(
                ns.fetch_file(f"http://{METADATA_IP}/latest/meta-data/", policy)
            )


class TestRedirectRevalidation:
    """Redirect hops must pass the same destination check."""

    def test_public_to_public_redirect_ok(self, pdf_server, monkeypatch):
        """A redirect between reachable hosts is followed successfully."""

        # Allow loopback so both hops can connect; we assert the redirect
        # was followed and the final body returned.
        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Redir(_RedirectHandler):
            location = f"http://127.0.0.1:{pdf_server}/final.pdf"

        srv, port = _start_server(Redir)
        try:
            data = asyncio.run(
                ns.fetch_file(f"http://127.0.0.1:{port}/start", _make_policy())
            )
        finally:
            srv.shutdown()
            srv.server_close()

        assert data == PDF_BODY

    def test_redirect_to_metadata_refused_on_hop(self, monkeypatch):
        """A reachable host that 302s to the metadata IP is refused.

        The initial hop (127.0.0.1) is allowed by the patched check, so the
        UrlPolicyError can only come from the redirect target being
        re-validated at connect time.
        """

        def blocked(ip):
            return str(ip) == METADATA_IP

        monkeypatch.setattr(ns, "is_blocked_ip", blocked)

        class Redir(_RedirectHandler):
            location = f"http://{METADATA_IP}/latest/meta-data/"

        srv, port = _start_server(Redir)
        try:
            with pytest.raises(ns.UrlPolicyError):
                asyncio.run(
                    ns.fetch_file(f"http://127.0.0.1:{port}/start", _make_policy())
                )
        finally:
            srv.shutdown()
            srv.server_close()

    def test_redirect_to_disallowed_scheme_refused_on_hop(self, monkeypatch):
        """A 302 to a scheme outside the allowlist is refused on the hop.

        Only the per-hop static policy re-check can produce this rejection:
        the redirect target uses ftp, which is never connectable, so the
        connect-time IP check is not what blocks it.
        """
        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Redir(_RedirectHandler):
            location = "ftp://example.invalid/x.pdf"

        srv, port = _start_server(Redir)
        try:
            with pytest.raises(ns.UrlPolicyError):
                asyncio.run(
                    ns.fetch_file(
                        f"http://127.0.0.1:{port}/start",
                        _make_policy(schemes=("http",)),
                    )
                )
        finally:
            srv.shutdown()
            srv.server_close()

    def test_redirect_to_ip_literal_refused_when_disallowed(self, monkeypatch):
        """A 302 to an IP literal is refused when allow_ip_hosts is False.

        The initial URL uses a hostname so it passes the pre-flight check;
        the redirect target IP is public (range-not-blocked), so only the
        per-hop re-application of the allow_ip_hosts rule rejects it.
        """
        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Redir(_RedirectHandler):
            location = "http://93.184.216.34/x.pdf"

        srv, port = _start_server(Redir)
        try:
            with pytest.raises(ns.UrlPolicyError):
                asyncio.run(
                    ns.fetch_file(
                        f"http://localhost:{port}/start",
                        _make_policy(allow_ip_hosts=False),
                    )
                )
        finally:
            srv.shutdown()
            srv.server_close()

    def test_too_many_redirects(self, monkeypatch):
        """Exceeding max_redirects raises instead of looping forever."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Redir(_RedirectHandler):
            location = "/loop"

        srv, port = _start_server(Redir)
        try:
            with pytest.raises(httpx2.TooManyRedirects):
                asyncio.run(
                    ns.fetch_file(
                        f"http://127.0.0.1:{port}/loop",
                        _make_policy(max_redirects=2),
                    )
                )
        finally:
            srv.shutdown()
            srv.server_close()


class TestSizeCap:
    """The hard byte cap must be enforced."""

    def test_content_length_precheck(self, monkeypatch):
        """A Content-Length above the cap aborts before reading the body."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Big(_Handler):
            def do_GET(self):
                self._send(b"%PDF-1.7\n" + b"x" * (5 * 1024 * 1024))

        srv, port = _start_server(Big)
        try:
            with pytest.raises(ns.DownloadSizeExceededError):
                asyncio.run(
                    ns.fetch_file(
                        f"http://127.0.0.1:{port}/big.pdf",
                        _make_policy(max_bytes=1024),
                    )
                )
        finally:
            srv.shutdown()
            srv.server_close()

    def test_mid_stream_abort(self, monkeypatch):
        """Without a Content-Length, the cap aborts mid-stream."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class NoLength(_Handler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.end_headers()
                self.wfile.write(b"%PDF-1.7\n" + b"x" * (2 * 1024 * 1024))

        srv, port = _start_server(NoLength)
        try:
            with pytest.raises(ns.DownloadSizeExceededError):
                asyncio.run(
                    ns.fetch_file(
                        f"http://127.0.0.1:{port}/big.pdf",
                        _make_policy(max_bytes=4096),
                    )
                )
        finally:
            srv.shutdown()
            srv.server_close()

    def test_within_cap_succeeds(self, pdf_server, monkeypatch):
        """A body under the cap is returned in full."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        data = asyncio.run(
            ns.fetch_file(
                f"http://127.0.0.1:{pdf_server}/x.pdf",
                _make_policy(max_bytes=len(PDF_BODY)),
            )
        )

        assert data == PDF_BODY


class TestContentValidation:
    """Content-type and magic-byte checks must reject non-PDF bodies."""

    def test_wrong_content_type_refused(self, monkeypatch):
        """A non-PDF Content-Type is refused even for PDF-like bytes."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Handler(_Handler):
            def do_GET(self):
                self._send(PDF_BODY, content_type="text/html")

        srv, port = _start_server(Handler)
        try:
            with pytest.raises(ns.UrlPolicyError):
                asyncio.run(ns.fetch_file(f"http://127.0.0.1:{port}/x", _make_policy()))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_content_type_with_parameters_accepted(self, pdf_server, monkeypatch):
        """'application/pdf; charset=...' is accepted (parameters stripped)."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Handler(_Handler):
            def do_GET(self):
                self._send(PDF_BODY, content_type="application/pdf; charset=utf-8")

        srv, port = _start_server(Handler)
        try:
            data = asyncio.run(
                ns.fetch_file(f"http://127.0.0.1:{port}/x", _make_policy())
            )
        finally:
            srv.shutdown()
            srv.server_close()

        assert data == PDF_BODY

    def test_bad_magic_bytes_refused(self, monkeypatch):
        """PDF Content-Type but non-PDF bytes is refused."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Handler(_Handler):
            def do_GET(self):
                self._send(b"this is not a pdf at all")

        srv, port = _start_server(Handler)
        try:
            with pytest.raises(ns.UrlPolicyError):
                asyncio.run(ns.fetch_file(f"http://127.0.0.1:{port}/x", _make_policy()))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_http_error_status_raises(self, monkeypatch):
        """A 404 response raises httpx2.HTTPError (not a policy error)."""

        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Handler(_Handler):
            def do_GET(self):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        srv, port = _start_server(Handler)
        try:
            with pytest.raises(httpx2.HTTPError):
                asyncio.run(ns.fetch_file(f"http://127.0.0.1:{port}/x", _make_policy()))
        finally:
            srv.shutdown()
            srv.server_close()


class TestProxyRequired:
    """URL fetching must be refused when no proxy/direct is configured."""

    def test_refused_when_proxy_unset(self, pdf_server):
        """proxy=None refuses before any network activity."""
        policy = _make_policy(proxy=None)

        with pytest.raises(ns.ProxyRequiredError):
            asyncio.run(ns.fetch_file(f"http://127.0.0.1:{pdf_server}/x.pdf", policy))


class TestAmbientProxyEnvIgnored:
    """Ambient HTTP(S)_PROXY env vars must not hijack egress.

    The transport is built with trust_env=False, so the only egress route
    in effect is the policy's explicit BIBRA_URL_PROXY (if any).
    """

    def test_direct_mode_ignores_ambient_proxy(self, pdf_server, monkeypatch):
        """With HTTP_PROXY/HTTPS_PROXY set, direct mode still goes direct."""
        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)
        sock, port, connections = _start_recording_proxy()
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{port}")
        try:
            data = asyncio.run(
                ns.fetch_file(f"http://127.0.0.1:{pdf_server}/x.pdf", _make_policy())
            )
        finally:
            sock.close()

        assert data == PDF_BODY
        assert connections == [], "direct mode leaked egress to ambient proxy"

    def test_explicit_proxy_still_used(self, pdf_server, monkeypatch):
        """An explicitly configured proxy is still routed through."""
        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)
        sock, port, connections = _start_recording_proxy()
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        try:
            # The recording proxy closes the connection, so the fetch fails
            # at the protocol level — but the connection attempt itself
            # proves the explicit proxy is in effect.
            with pytest.raises(httpx2.HTTPError):
                asyncio.run(
                    ns.fetch_file(
                        f"http://127.0.0.1:{pdf_server}/x.pdf",
                        _make_policy(proxy=f"http://127.0.0.1:{port}"),
                    )
                )
        finally:
            sock.close()

        assert len(connections) >= 1, "explicit proxy was not used"


class TestProxyModeDnsCheck:
    """The connect-time resolved-IP check applies in direct mode only.

    In proxy mode the proxy's own egress allowlist is the authoritative
    control; a local getaddrinfo of the target is skipped (no false
    positives from resolver differences, no unexpected local DNS lookup).
    """

    def test_proxy_mode_skips_local_dns_check(self, monkeypatch):
        """In proxy mode no local getaddrinfo of the target is performed."""
        calls = []

        def _boom(*args, **kwargs):
            calls.append(args)
            raise socket.gaierror("must not be called in proxy mode")

        monkeypatch.setattr(socket, "getaddrinfo", _boom)
        sock, port, _ = _start_recording_proxy()
        try:
            # The dummy proxy closes the connection, so the fetch fails at
            # the protocol level — but it must get there without a local
            # DNS lookup of the target (no UrlPolicyError / ConnectError
            # from our check, only the proxy's protocol failure).
            with pytest.raises(httpx2.HTTPError) as exc_info:
                asyncio.run(
                    ns.fetch_file(
                        "http://some-unresolvable-host.invalid/x.pdf",
                        _make_policy(proxy=f"http://127.0.0.1:{port}"),
                    )
                )
        finally:
            sock.close()

        assert calls == [], "proxy mode performed a local DNS lookup"
        assert not isinstance(exc_info.value, ns.UrlPolicyError)

    def test_direct_mode_still_runs_dns_check(self, monkeypatch):
        """In direct mode the resolved-IP check still runs (via getaddrinfo)."""
        calls = []
        real = socket.getaddrinfo

        def _counting(*args, **kwargs):
            calls.append(args)
            return real(*args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", _counting)
        monkeypatch.setattr(ns, "is_blocked_ip", lambda ip: False)

        class Handler(_Handler):
            def do_GET(self):
                self._send(PDF_BODY)

        srv, port = _start_server(Handler)
        try:
            data = asyncio.run(
                ns.fetch_file(f"http://localhost:{port}/x.pdf", _make_policy())
            )
        finally:
            srv.shutdown()
            srv.server_close()

        assert data == PDF_BODY
        assert len(calls) >= 1, "direct mode skipped the resolved-IP check"
