# STRIDE threat model

Scope: the PolicyScan API (FastAPI), its database, the policy fetcher, and the tracker audit worker (headless Chromium).

## Assets

- User accounts (email, argon2 password hash) and saved reports.
- The server's network position: it makes outbound requests to user-supplied URLs.
- The server's secrets (session signing key, database password).
- Integrity of scores (users rely on them).

## Trust boundaries

1. Internet -> API (all input untrusted).
2. API -> arbitrary websites (fetched HTML and policy text are untrusted).
3. API -> audit worker (separate container; worker loads hostile pages).
4. API -> database.

## Threats and mitigations

| # | STRIDE | Threat | Mitigation | Where | Test |
| --- | --- | --- | --- | --- | --- |
| 1 | Elevation / Info disclosure | **SSRF**: user submits internal URLs (localhost, 10/8, 169.254.169.254 cloud metadata) | `validate_url` resolves DNS, rejects any non-public address (one bad answer rejects the host), http/https on ports 80/443 only, no credentials in URL; re-validated after every redirect; redirect and size caps | `app/core/ssrf.py`, `app/services/policy_fetcher.py` | `tests/test_ssrf.py`, `tests/test_fetcher.py` |
| 2 | Elevation | **DNS rebinding** between check and connect | Connection is pinned to the validated IP (Host header and SNI keep the real name) | `policy_fetcher.safe_get` | `test_connection_is_pinned_to_validated_ip` |
| 3 | Elevation | Browser in the audit worker reaches internal addresses via subresources or redirects | Every request the page makes is routed through `validate_url`; private targets are aborted | `tracker_audit.py` | manual (live) |
| 4 | Elevation / DoS | Hostile page attacks the worker (browser exploit, crypto-miner, huge download) | Worker runs in its own container: no DB, no `.env`, own network, read-only filesystem, all capabilities dropped, no-new-privileges, CPU/memory/pids limits, navigation timeout, downloads disabled | `docker/docker-compose.yml`, `tracker_audit.py` | not yet verified under Docker (see security-report.md) |
| 5 | Tampering / XSS | Fetched policy text or tracker names contain markup/script | UI inserts all dynamic text with `textContent` only; strict CSP (`script-src 'self'`, no inline script/style); `X-Content-Type-Options: nosniff` | `web/app.js`, `app/main.py` | `test_index_has_no_inline_script_or_style`, headers tests, browser run with no CSP violations |
| 6 | Spoofing | Credential stuffing, weak passwords | argon2 hashing, min length 10, generic login error, constant-time-ish check (dummy hash for unknown emails), rate limits, failed logins audited | `routes.py`, `security.py` | `test_register_login_logout`, `test_passwords_are_hashed_with_argon2` |
| 7 | Spoofing / Tampering | Session theft or CSRF | Signed session cookie: HttpOnly, SameSite=Lax, Secure outside dev; new session on login; cross-origin state-changing requests rejected by Origin check | `app/main.py` | `test_session_cookie_flags`, `test_cross_origin_post_blocked` |
| 8 | Info disclosure | One user reads another's reports | Reports are looked up by owner; others get 404 (not 403) | `routes._owned_report` | `test_reports_are_private_to_owner` |
| 9 | DoS | Scan endpoint used to hammer sites or exhaust workers | Per-IP and per-user rate limits, stricter limit on `/api/scan`, input size limits (200k chars, 2k URL), fetch timeout and size cap | `security.py`, `routes.py` | `test_scan_rate_limit`, `test_input_validation` |
| 10 | Repudiation | No record of who did what | `audit_log` table: register, login, failed login, scan (user, IP, time) | `db/models.py` | covered indirectly |
| 11 | Info disclosure | Over-retention of user data | Unsaved reports purged after 30 days at startup | `models.purge_unsaved` | `test_purge_unsaved_after_30_days` |
| 12 | Info disclosure | Secrets in repo or weak default secret | `.env` gitignored; app refuses to start outside dev with the default secret | `app/main.py`, `.gitignore` | manual |
| 13 | Tampering | Prompt injection | No LLM is used. If one is added, policy text must be treated as untrusted and output grounded in classified segments | n/a | n/a |
| 14 | Info disclosure | Malicious model file | `joblib` loads only from the configured local `models/` directory written by our own training script | `classifier.py` | n/a |

## Known gaps and residual risks

- Rate limiting is in memory, per process. Behind multiple workers or a proxy it needs Redis and a trusted-proxy setting; `X-Forwarded-For` is deliberately ignored today, so behind a reverse proxy all users share one IP bucket.
- Anonymous reports are readable by anyone who holds the (random UUID) report id.
- No TOTP MFA yet (optional in the spec).
- Database tables are created with `create_all`; Alembic migrations are not set up yet.
- HTTPS is not terminated by the app; deploy behind a TLS proxy. HSTS is already sent.
- The audit worker isolation settings have been written but not yet exercised in a running Docker environment.
- ZAP baseline scan has not been run yet.
