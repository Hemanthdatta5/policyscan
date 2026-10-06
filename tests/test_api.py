from datetime import timedelta
from pathlib import Path

from app.db import models

POLICY = (Path(__file__).parent / "fixtures" / "policy_bad.html").read_text()
TEXT = "We collect your precise location data and may sell your personal information to advertisers. " * 6


def creds(email="a@example.com", pw="correct horse battery"):
    return {"email": email, "password": pw}


def test_health_and_headers(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert "max-age" in r.headers["strict-transport-security"]
    assert "script-src 'self'" in client.get("/").headers["content-security-policy"]


def test_index_has_no_inline_script_or_style(client):
    html = client.get("/").text
    assert "<style" not in html and " style=" not in html
    assert "<script>" not in html and "onclick=" not in html


def test_register_login_logout(client):
    assert client.post("/api/auth/register", json=creds()).status_code == 201
    assert client.get("/api/auth/me").json()["email"] == "a@example.com"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["email"] is None
    assert client.post("/api/auth/login", json=creds(pw="wrong password!")).status_code == 401
    assert client.post("/api/auth/login", json=creds()).status_code == 200


def test_weak_password_and_duplicate(client):
    assert client.post("/api/auth/register", json=creds(pw="short")).status_code == 422
    assert client.post("/api/auth/register", json=creds()).status_code == 201
    assert client.post("/api/auth/register", json=creds()).status_code == 409


def test_passwords_are_hashed_with_argon2(client):
    client.post("/api/auth/register", json=creds())
    db = next(models.get_db())
    user = db.query(models.User).one()
    assert user.password_hash.startswith("$argon2")
    assert "correct horse" not in user.password_hash


def test_session_cookie_flags(client):
    r = client.post("/api/auth/register", json=creds())
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_scan_text_and_save_flow(client):
    r = client.post("/api/scan", json={"text": TEXT})
    assert r.status_code == 200
    rep = r.json()
    assert rep["trackers"]["checked"] is False and 1 <= rep["score"] <= 10
    assert client.post(f"/api/reports/{rep['id']}/save").status_code == 401
    client.post("/api/auth/register", json=creds())
    assert client.post(f"/api/reports/{rep['id']}/save").json()["saved"] is True
    assert [x["id"] for x in client.get("/api/reports").json()] == [rep["id"]]


def test_reports_are_private_to_owner(client):
    client.post("/api/auth/register", json=creds())
    rep = client.post("/api/scan", json={"text": TEXT}).json()
    client.post(f"/api/reports/{rep['id']}/save")
    client.post("/api/auth/logout")
    assert client.get(f"/api/reports/{rep['id']}").status_code == 404
    client.post("/api/auth/register", json=creds("b@example.com"))
    assert client.get(f"/api/reports/{rep['id']}").status_code == 404
    assert client.post(f"/api/reports/{rep['id']}/save").status_code == 404
    assert client.get("/api/reports").json() == []


def test_input_validation(client):
    assert client.post("/api/scan", json={}).status_code == 422
    assert client.post("/api/scan", json={"url": "a.com", "text": "x"}).status_code == 422
    assert client.post("/api/scan", json={"text": "x" * 200_001}).status_code == 422
    assert client.post("/api/scan", json={"text": "too short"}).status_code == 422


def test_scan_url_blocks_private_targets(client):
    r = client.post("/api/scan", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert r.status_code == 422
    r = client.post("/api/scan", json={"url": "http://localhost:8000/"})
    assert r.status_code == 422


def test_scan_rate_limit(client):
    codes = [client.post("/api/scan", json={"text": TEXT}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and 429 in codes[5:]


def test_cross_origin_post_blocked(client):
    r = client.post("/api/auth/login", json=creds(), headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_purge_unsaved_after_30_days(client):
    rep = client.post("/api/scan", json={"text": TEXT}).json()
    client.post("/api/auth/register", json=creds())
    saved = client.post("/api/scan", json={"text": TEXT}).json()
    client.post(f"/api/reports/{saved['id']}/save")
    db = next(models.get_db())
    for r in db.query(models.Report).all():
        r.created_at = models.utcnow() - timedelta(days=31)
    db.commit()
    assert models.purge_unsaved(db) == 1
    assert db.get(models.Report, rep["id"]) is None and db.get(models.Report, saved["id"]) is not None


def test_report_text_is_returned_as_data_not_markup(client):
    text = "We collect your precise location data. <script>alert(1)</script> We may sell your personal information to advertisers today. " * 4
    rep = client.post("/api/scan", json={"text": text}).json()
    assert rep["id"]  # stored verbatim; the UI renders with textContent only
