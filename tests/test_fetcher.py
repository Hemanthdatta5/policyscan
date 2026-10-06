from pathlib import Path

import httpx
import pytest

from app.services import policy_fetcher as pf

FIX = Path(__file__).parent / "fixtures"
PUBLIC = lambda host, port: ["93.184.216.34"]


def transport(routes: dict):
    """routes maps (host, path) -> (status, headers, body). Requests arrive pinned to the IP,
    with the real name in the Host header."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        host = req.headers["host"]
        seen.append((str(req.url), host))
        status, headers, body = routes.get((host, req.url.path), (404, {}, "nf"))
        return httpx.Response(status, headers=headers, content=body)

    t = httpx.MockTransport(handler)
    t.seen = seen
    return t


def test_connection_is_pinned_to_validated_ip():
    t = transport({("example.com", "/"): (200, {"content-type": "text/html"}, "hi")})
    r = pf.safe_get("https://example.com/", resolver=PUBLIC, transport=t)
    assert r.text == "hi"
    assert t.seen[0][0].startswith("https://93.184.216.34/")


def test_redirect_to_private_blocked():
    def resolver(host, port):
        return ["10.0.0.1"] if host == "internal.test" else ["93.184.216.34"]

    t = transport({("example.com", "/"): (302, {"location": "http://internal.test/admin"}, "")})
    with pytest.raises(pf.FetchError, match="blocked"):
        pf.safe_get("http://example.com/", resolver=resolver, transport=t)


def test_redirect_to_metadata_ip_blocked():
    t = transport({("example.com", "/"): (302, {"location": "http://169.254.169.254/latest/"}, "")})
    with pytest.raises(pf.FetchError, match="blocked"):
        pf.safe_get("http://example.com/", resolver=lambda h, p: [h] if h[0].isdigit() else ["93.184.216.34"], transport=t)


def test_redirect_loop_capped():
    t = transport({("example.com", "/"): (302, {"location": "http://example.com/"}, "")})
    with pytest.raises(pf.FetchError, match="redirects"):
        pf.safe_get("http://example.com/", resolver=PUBLIC, transport=t)


def test_response_size_capped(monkeypatch):
    monkeypatch.setenv("POLICYSCAN_FETCH_MAX_BYTES", "1000")
    from app.core.config import get_settings

    get_settings.cache_clear()
    t = transport({("example.com", "/"): (200, {"content-type": "text/html"}, "x" * 5000)})
    with pytest.raises(pf.FetchError, match="too large"):
        pf.safe_get("http://example.com/", resolver=PUBLIC, transport=t)
    get_settings.cache_clear()


def test_find_policy_links_ranks_privacy_policy_first():
    html = '<a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/legal/privacy-policy">Privacy Policy</a>'
    links = pf.find_policy_links(html, "https://example.com/")
    assert links[0] == "https://example.com/legal/privacy-policy"


def test_fetch_policy_end_to_end_and_robots():
    policy = (FIX / "policy_bad.html").read_text() + "<p>" + "filler " * 100 + "</p>"
    t = transport({
        ("example.com", "/"): (200, {"content-type": "text/html"}, '<a href="/privacy">Privacy Policy</a>'),
        ("example.com", "/robots.txt"): (200, {"content-type": "text/plain"}, "User-agent: *\nDisallow: /secret"),
        ("example.com", "/privacy"): (200, {"content-type": "text/html"}, policy),
    })
    res = pf.fetch_policy("example.com", resolver=PUBLIC, transport=t)
    assert res.url == "https://example.com/privacy"


def test_robots_disallow_respected():
    t = transport({("example.com", "/robots.txt"): (200, {}, "User-agent: *\nDisallow: /privacy")})
    assert not pf.robots_allows("https://example.com/privacy", resolver=PUBLIC, transport=t)
