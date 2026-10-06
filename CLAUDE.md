# PolicyScan

PolicyScan is a capstone project (MSIST: data science + information security) for a team of three. It reads a website's privacy policy, checks what the website actually does with visitor data, and gives a privacy score from 1 to 10 with the reason behind every lost point.

The core idea, and the project's main contribution: **compare what the policy says with what the site does.** Existing tools either summarize policies (ToS;DR) or block trackers (uBlock, Ghostery). None check one against the other.

## Users and the core flow

1. User enters a website address (or pastes policy text).
2. App finds the privacy policy page, downloads it, strips page clutter, splits it into paragraphs.
3. NLP model classifies each paragraph into OPP-115 data-practice categories.
4. App loads the website in an isolated headless browser and records third-party requests, cookies, and scripts, before and after the cookie banner.
5. App matches third-party domains against tracker lists and compares them with what the policy discloses.
6. App computes the 1-10 score and shows: grade, category breakdown, red flags with the exact policy quote, tracker table (disclosed / not in policy), GDPR/CCPA checklist.
7. Report is saved; users can log in to see saved reports.

Pasted text skips steps 4-5; the Policy vs. practice category is marked "not checked" and the score is scaled to 10.

## Scoring (must match the proposal exactly)

Total 10 points across six categories:

| Category | Points | Full points when | Points lost when |
| --- | --- | --- | --- |
| Data collection | 2 | Only needed data is collected | Location, contacts, biometrics, health, or browsing history collected |
| Data sharing | 2 | No selling; partners named | Sells data, shares with advertisers or unnamed "partners" |
| User rights | 1.5 | Users can access and delete their data | No access or deletion rights |
| Data retention | 1 | A clear time limit is stated | "As long as necessary", indefinite, or not stated |
| Security & clarity | 1 | Encryption/safeguards described in plain words | Vague hedge words ("may", "certain", "from time to time"), no security details |
| Policy vs. practice | 2.5 | Trackers found match the policy | Site loads trackers the policy never mentions |

Ratings: 8-10 Good, 5-7 Fair, 1-4 Poor. Every lost point must carry a reason and, where possible, the policy sentence that caused it. Keep scoring weights in one config file so they are easy to tune and document.

## Architecture

```
User browser (web UI)
   -> FastAPI gateway: auth, rate limiting, input validation, SSRF filter
        -> Policy pipeline: find policy link, fetch, clean (trafilatura), segment
             -> NLP classifier (baseline TF-IDF + LogReg; DistilBERT fine-tuned)
        -> Tracker audit worker: Playwright Chromium in an isolated container, timeouts
             -> Tracker matcher (EasyPrivacy + DuckDuckGo Tracker Radar)
   -> Risk scorer: categories + policy-vs-practice comparison + explanations
   -> PostgreSQL (SQLite in dev): users, reports, audit log
```

## Tech stack

- Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic
- Front end: decide with the user before building (FastAPI-served single page vs. Streamlit vs. React). Default if not decided: a FastAPI-served HTML/JS page styled like `demo/policyscan.html`.
- Policy fetching: httpx, trafilatura / BeautifulSoup
- Tracker audit: Playwright (Chromium), run in Docker for isolation
- ML: scikit-learn, Hugging Face Transformers + PyTorch (DistilBERT), SHAP for explanations
- DB: PostgreSQL (Docker Compose), SQLite for local dev and tests
- Auth: argon2/bcrypt password hashing, session or JWT, optional TOTP MFA
- Tests: pytest; security: Bandit, pip-audit, OWASP ZAP baseline scan

## Data

- **OPP-115** (Wilson et al., 2016): 115 policies, ~3,700 paragraphs labeled into 10 categories. Download from https://usableprivacy.org/data (OPP-115 Corpus). Put raw data in `data/raw/` (gitignored). Write a loader that turns the consolidated annotations into a paragraph-level, multi-label CSV.
- Map OPP-115 categories onto the six score categories (document the mapping in `ml/category_map.py`): First Party Collection/Use -> collection; Third Party Sharing/Collection -> sharing; User Access, Edit & Deletion + User Choice/Control -> rights; Data Retention -> retention; Data Security -> security; Policy Change, Do Not Track, International & Specific Audiences, Other -> informational.
- Classifier labels the category; sub-signals inside a category (sells data, advertising, precise location, retention period present, hedge words) come from a rules layer on top. Keep both layers and make the report say which produced each flag.
- **Tracker lists:** EasyPrivacy (https://easylist.to/easylist/easyprivacy.txt) and DuckDuckGo Tracker Radar (https://github.com/duckduckgo/tracker-radar). Cache locally; include a small vendored fallback list so tests run offline.
- **Validation:** ToS;DR grades for 20-30 popular services (case study).

## ML requirements

- Split by **policy**, not by paragraph (70/15/15), to prevent leakage. Fix the random seed.
- Multi-label classification. Baseline: TF-IDF + one-vs-rest Logistic Regression. Then fine-tune DistilBERT (3-5 epochs; script must run on Google Colab free GPU and on CPU for a tiny smoke test).
- Report per-category precision/recall/F1, micro and macro F1, baseline vs. DistilBERT. Target micro-F1 >= 0.75.
- Handle class imbalance (class weights, per-category thresholds tuned on validation).
- Save models to `models/` (gitignored) with a version tag; the API loads whichever model is configured.

## Security requirements (non-negotiable)

- **SSRF protection** on every outbound fetch: resolve DNS, reject private, loopback, link-local, and cloud metadata addresses (169.254.169.254, etc.), re-check after every redirect, allow only http/https on ports 80/443, cap redirects and response size.
- Tracker audits run in a separate container with no access to the app's network or secrets, strict timeouts, no downloads, limited CPU/memory.
- Treat all fetched HTML/policy text as untrusted: escape on output (no innerHTML with fetched content), strict Content-Security-Policy.
- Rate limiting per IP and per user; input validation on all endpoints.
- Passwords hashed with argon2 or bcrypt; secure, HttpOnly, SameSite cookies; HTTPS in deployment; security headers (CSP, HSTS, X-Content-Type-Options).
- If an LLM is ever added for summaries, treat policy text as untrusted (prompt injection) and ground output in classified segments.
- Respect robots.txt and site terms; public pages only; no login bypass; polite request rates.
- Data minimization: delete unsaved reports after 30 days.
- Maintain a STRIDE threat model in `docs/threat-model.md`. Run Bandit, pip-audit, and an OWASP ZAP baseline scan before each milestone; record results in `docs/security-report.md`.
- PolicyScan output is informational, not legal advice. Say so in the UI.

## Suggested layout

```
app/            FastAPI app (api/, core/config.py, core/security.py, db/, services/)
app/services/   policy_fetcher.py, segmenter.py, classifier.py, rules.py, tracker_audit.py, tracker_match.py, scorer.py
ml/             data loader, category map, train_baseline.py, train_distilbert.py, evaluate.py
web/            front end
tests/          unit tests (scorer, rules, SSRF filter, tracker matching) + fixtures (saved policy HTML, saved HAR files)
docker/         Dockerfiles for api and audit worker; docker-compose.yml
docs/           threat-model.md, security-report.md, model-evaluation.md, case-study.md
demo/           policyscan.html (front-end prototype from the proposal)
```

## How to work in this repo

- Build in the milestone order below; get each slice working end to end with tests before polishing.
- Tests must run offline using saved fixtures (policy HTML, recorded tracker lists, recorded network logs). Live scans are integration tests marked `@pytest.mark.live`.
- Keep the scorer pure (inputs in, score + reasons out) so it is easy to unit test and explain.
- Write a README with one-command setup (`docker compose up`) and a no-Docker dev path.

## Milestones (7 weeks, three roles)

| Stage | Weeks | Work | Owner |
| --- | --- | --- | --- |
| 1 Plan & prepare | 1-3 | Repo, config, OPP-115 loader + category map, policy fetcher with SSRF filter, scorer with rules layer, tracker list loader | Data Scientist, Security Engineer |
| 2 Build | 4-6 | Baseline classifier + evaluation, DistilBERT training script, Playwright audit worker in Docker, comparison logic, API, web UI, auth + saved reports | All |
| 3 Test & deliver | 7 | Security scans + fixes, case study of 20-30 sites vs. ToS;DR, docs, demo | Project Manager leads |

Roles: Project Manager (schedule, risks, testing, case study, final report), Data Scientist (data, models, scoring), Security Engineer (app, audit worker, security).
