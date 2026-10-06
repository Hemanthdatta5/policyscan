"""Load a site in headless Chromium and record third-party requests, before and after the
cookie banner. Intended to run in the isolated audit-worker container (app/audit_worker.py).
"""

from urllib.parse import urlsplit

from app.core.ssrf import SSRFError, validate_url
from app.services.tracker_match import is_third_party

NAV_TIMEOUT_MS = 20_000
SETTLE_MS = 3_000
ACCEPT_WORDS = ("accept all", "accept", "agree", "allow all", "i agree", "got it", "ok")


class AuditError(Exception):
    pass


def render_page_text(page_url: str) -> str:
    return render_page(page_url)["text"]


def render_page(page_url: str) -> dict:
    """Render a page in the browser and return {"text", "links": [[text, href], ...]}. Used for
    policies the static fetch cannot read (JavaScript-built pages, bot-blocked sites) and to find
    policy links. Same SSRF checks as the audit; downloads disabled."""
    try:
        target = validate_url(page_url)
    except SSRFError as exc:
        raise AuditError(f"blocked: {exc}") from exc
    from playwright.sync_api import sync_playwright

    def guard(route):
        try:
            validate_url(route.request.url)
        except SSRFError:
            return route.abort()
        route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            page = browser.new_context(accept_downloads=False).new_page()
            page.route("**/*", guard)
            try:
                page.goto(target.url, timeout=NAV_TIMEOUT_MS, wait_until="load")
                page.wait_for_timeout(SETTLE_MS)
                links = page.eval_on_selector_all(
                    "a[href]", "els => els.slice(0, 600).map(e => [(e.innerText || e.getAttribute('aria-label') || '').slice(0, 120), e.href])"
                )
                return {"text": page.inner_text("body")[:500_000], "links": links}
            except Exception as exc:
                raise AuditError(f"page did not render: {type(exc).__name__}") from exc
        finally:
            browser.close()


def run_audit(site_url: str) -> dict:
    """Return {"site_host", "before": [hosts], "after": [hosts], "cookies": n, "banner_clicked": bool}."""
    if "://" not in site_url:
        site_url = "https://" + site_url
    try:
        target = validate_url(site_url)
    except SSRFError as exc:
        raise AuditError(f"blocked: {exc}") from exc
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise AuditError("playwright is not installed") from exc

    site_host = target.host
    phase = {"name": "before"}
    seen: dict[str, set[str]] = {"before": set(), "after": set()}

    def on_route(route):
        host = urlsplit(route.request.url).hostname or ""
        try:
            validate_url(route.request.url)
        except SSRFError:
            return route.abort()  # never let the page reach private addresses
        if host and is_third_party(host, site_host):
            seen[phase["name"]].add(host)
        route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            ctx = browser.new_context(accept_downloads=False, java_script_enabled=True)
            page = ctx.new_page()
            page.route("**/*", on_route)
            try:
                page.goto(target.url, timeout=NAV_TIMEOUT_MS, wait_until="load")
            except Exception as exc:
                raise AuditError(f"page did not load: {type(exc).__name__}") from exc
            page.wait_for_timeout(SETTLE_MS)
            clicked = False
            phase["name"] = "after"
            for word in ACCEPT_WORDS:
                btn = page.get_by_role("button", name=word, exact=False).first
                try:
                    if btn.is_visible(timeout=300):
                        btn.click(timeout=1500)
                        clicked = True
                        break
                except Exception:  # nosec B112 - button absent/not clickable: try the next label
                    continue
            page.wait_for_timeout(SETTLE_MS)
            cookies = len(ctx.cookies())
        finally:
            browser.close()
    return {
        "site_host": site_host,
        "before": sorted(seen["before"]),
        "after": sorted(seen["after"] - seen["before"]),
        "cookies": cookies,
        "banner_clicked": clicked,
    }
