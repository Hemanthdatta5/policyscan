# Security report

## Milestone: MVP (2026-10-05)

| Check | Result |
| --- | --- |
| Unit and integration tests (pytest, offline) | 74 passed. Includes SSRF filter, redirect re-check, IP pinning, size/redirect caps, auth, session flags, cross-user access, rate limits, CSRF origin check, retention purge |
| Bandit (`bandit -r app ml`) | No issues identified. Fixed: `assert` in config replaced by an explicit check. Suppressed with a reason: B112 in the cookie-banner click loop (a missing button is expected); B615 on Hugging Face downloads in the training-only script (pin a revision for releases) |
| pip-audit | No known vulnerabilities in installed dependencies. (An earlier run flagged only the venv's own `pip` 25.2; upgraded.) |
| OWASP ZAP baseline | **Not run.** Docker Desktop was not running on the development machine, so the ZAP container could not start. Run before the final milestone: `docker run --rm -t zaproxy/zap-stable zap-baseline.py -t http://host.docker.internal:8000` |
| Docker isolation of the audit worker | **Not verified.** The compose file validates (`docker compose config`) but the images were not built or run here |
| Manual browser check | UI run in headless Chromium: scan, register, save, saved list; zero console errors and zero CSP violations |

## Findings still open

1. Run the ZAP baseline scan and record results here.
2. Build and run the Docker stack; confirm the audit container cannot reach the database or API secrets, and that the API can reach only `audit:9000`.
3. Move rate limiting to a shared store before running more than one process.
4. Add Alembic migrations before the schema changes.
5. Optional TOTP MFA.

## How to re-run

```
.venv\Scripts\python -m pytest
.venv\Scripts\python -m bandit -r app ml
.venv\Scripts\python -m pip_audit
```
