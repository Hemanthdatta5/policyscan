from fastapi.testclient import TestClient

from app.core.scoring_config import CATEGORY_POINTS, TOTAL_POINTS
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_security_headers_on_index():
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_scoring_weights_sum_to_ten():
    assert TOTAL_POINTS == 10.0
    assert CATEGORY_POINTS["policy_vs_practice"] == 2.5
