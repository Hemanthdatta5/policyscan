# PolicyScan

Reads a website's privacy policy, checks what the site actually does with visitor data, and gives it a privacy score from 1 to 10 with the reason behind every lost point. The main idea: **compare what the policy says with what the site does.** See [CLAUDE.md](CLAUDE.md) for the full spec.

*Output is informational, not legal advice.*

## What works today (MVP)

- Enter a website or paste policy text. The app finds the policy page (respecting robots.txt), cleans it, splits it into paragraphs, and classifies each one.
- Classifier: TF-IDF + Logistic Regression trained on OPP-115 (micro-F1 0.785 on held-out policies, see [docs/model-evaluation.md](docs/model-evaluation.md)). Falls back to a keyword classifier if no model is present.
- Rules layer finds sub-signals (sells data, location, no deletion right, vague hedge words, ...) and quotes the exact sentence. Every flag says which layer found it.
- Tracker audit: headless Chromium loads the site before and after the cookie banner; third-party hosts are matched against a vendored tracker list (plus EasyPrivacy if cached) and compared with the companies the policy names.
- Score: six categories, weights in [app/core/scoring_config.py](app/core/scoring_config.py). Pasted text skips the tracker check and the score is scaled to 10.
- Accounts (argon2), saved reports, per-IP/per-user rate limits, strict CSP, SSRF-safe fetching.
- Not done yet: DistilBERT results (script is ready), ZAP scan, Docker stack verification, TOTP MFA. See [docs/security-report.md](docs/security-report.md).

## Dev setup (no Docker)

```
python -m venv .venv
.venv\Scripts\activate                       # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev,ml,audit]"
playwright install chromium
copy .env.example .env
uvicorn app.main:app --reload                # http://localhost:8000
pytest
```

### Train the classifier (optional but recommended)

```
# download OPP-115 from https://usableprivacy.org/data and unzip into data/raw/ (gives data/raw/OPP-115)
python -m ml.load_opp115          # paragraph-level multi-label CSV
python -m ml.train_baseline       # saves models/baseline-v0 and writes docs/model-evaluation.md
python -m ml.train_distilbert --smoke      # CPU smoke test; needs pip install -e ".[transformers]"
python -m ml.train_distilbert --epochs 4   # on Colab GPU
```

### Case study vs. ToS;DR

```
python -m ml.case_study           # writes docs/case-study.md (live network, takes a few minutes)
```

## Docker

```
copy .env.example .env            # set POLICYSCAN_SECRET_KEY and POSTGRES_PASSWORD
docker compose --env-file .env -f docker/docker-compose.yml up --build
```

Three services: `db` (Postgres), `api`, and `audit` (Chromium worker on its own network with no secrets, read-only filesystem and resource limits). Open http://localhost:8000.

## Layout

`app/` API and services, `ml/` data loader, category map, training and case study, `web/` front end (no inline scripts or styles), `tests/` offline tests and fixtures, `docker/` images and compose, `docs/` threat model, security, evaluation and case-study reports, `demo/` the original prototype.

Tests run offline. Live-network tests are marked `@pytest.mark.live` and skipped by default (`pytest -m live`).

## Known limitations

- Policies that live on a separate page from the one linked (e.g. a landing page linking to the full text) are scored on the linked page only.
- Sites that block our crawler (e.g. Wikipedia, Facebook) can't be scanned; paste the text instead.
- Tracker disclosure is by company name in the policy; "advertising partners" without a name counts as not disclosed.
- Rules are heuristics: the GDPR/CCPA checklist is a keyword check, not a legal assessment.
