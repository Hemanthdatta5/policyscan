"""Integration tests that hit the real network. Run with: pytest -m live"""

import pytest

from app.services.scan import scan_url

pytestmark = pytest.mark.live


@pytest.mark.parametrize("site", ["wikipedia.org", "duckduckgo.com"])
def test_live_scan(site):
    rep = scan_url(site)
    assert 1 <= rep["score"] <= 10
    assert rep["policy_url"].startswith("https://")
    assert rep["paragraph_count"] > 3
