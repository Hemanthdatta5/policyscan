"""Orchestrates one scan: fetch -> clean -> segment -> classify -> rules -> audit -> score."""

from collections import Counter
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.services import (
    classifier,
    policy_fetcher,
    rules,
    scorer,
    segmenter,
    tracker_audit,
    tracker_match,
)

DISCLAIMER = "PolicyScan output is informational, not legal advice."
MIN_POLICY_CHARS = 300
MIN_STATIC_CHARS = 4000  # shorter than this from a static fetch -> try rendering the page


class ScanError(Exception):
    """User-facing scan failure."""


def _audit(site_url: str) -> dict:
    if get_settings().audit_worker_url:
        return _call_worker("/audit", site_url, 90)
    return tracker_audit.run_audit(site_url)


def _call_worker(path: str, url: str, timeout: float) -> dict:
    s = get_settings()
    try:
        resp = httpx.post(f"{s.audit_worker_url.rstrip('/')}{path}", json={"url": url}, timeout=timeout)
    except httpx.HTTPError as exc:
        raise tracker_audit.AuditError("audit worker unreachable") from exc
    if resp.status_code != 200:
        raise tracker_audit.AuditError(resp.json().get("detail", "audit failed"))
    return resp.json()


def _render_full(page_url: str) -> dict:
    if get_settings().audit_worker_url:
        return _call_worker("/render", page_url, 60)
    return tracker_audit.render_page(page_url)


def _render(page_url: str) -> str:
    return _render_full(page_url)["text"]


MIN_RENDERED_POLICY_CHARS = 1500


def _discover_in_browser(site_url: str) -> tuple[str, str] | None:
    """Fallback for sites that block the plain HTTP fetch: let the isolated browser load the
    home page, find the privacy link, and read the policy. robots.txt is still respected."""
    if "://" not in site_url:
        site_url = "https://" + site_url
    try:
        home = _render_full(site_url)
    except tracker_audit.AuditError:
        return None
    for link in policy_fetcher.rank_policy_links([tuple(x) for x in home["links"]], site_url)[:3]:
        if not policy_fetcher.robots_allows(link):
            continue
        try:
            text = _render(link)
        except tracker_audit.AuditError:
            continue
        if len(text) >= MIN_RENDERED_POLICY_CHARS:
            return link, text
    return None


def build_report(
    paragraphs: list[str], *, source: str, url: str | None, policy_url: str | None, audit: dict | None, audit_error: str | None
) -> dict:
    if sum(len(p) for p in paragraphs) < MIN_POLICY_CHARS:
        raise ScanError("The policy text is too short to analyze.")
    labels, clf_name = classifier.classify(paragraphs)
    counts = Counter(lab for labs in labels for lab in labs)
    sig = rules.run_rules(paragraphs, labels)

    trackers: dict | None = None
    tracker_view: dict = {"checked": False, "findings": [], "error": audit_error}
    if audit is not None:
        hosts = {h: "before" for h in audit["before"]} | {h: "after" for h in audit["after"]}
        trackers = tracker_match.compare_with_policy(hosts, " ".join(paragraphs), audit["site_host"])
        tracker_view = {
            "checked": True,
            "findings": trackers["findings"],
            "third_party_hosts": len(hosts),
            "cookies": audit["cookies"],
            "banner_clicked": audit["banner_clicked"],
            "error": None,
        }

    result = scorer.score_policy(sig, trackers)
    return {
        "source": source,
        "url": url,
        "policy_url": policy_url,
        "classifier": clf_name,
        "paragraph_count": len(paragraphs),
        "category_counts": dict(counts),
        "signals": {
            "negative": [s.name for s in sig["negatives"]],
            "positive": sorted(sig["positives"]),
            "layer": "rules",
        },
        "checklist": sig["checklist"],
        "trackers": tracker_view,
        "disclaimer": DISCLAIMER,
        **result,
    }


def scan_url(site_url: str) -> dict:
    audit_on = get_settings().enable_audit
    policy_url, text = "", ""
    try:
        fetched = policy_fetcher.fetch_policy(site_url)
        policy_url, text = fetched.url, segmenter.html_to_text(fetched.text)
        if len(text) < MIN_STATIC_CHARS and audit_on:
            # Probably a JavaScript-rendered page: render it in the isolated browser instead.
            try:
                text = _render(fetched.url)
            except tracker_audit.AuditError:
                pass
    except policy_fetcher.FetchError as exc:
        found = _discover_in_browser(site_url) if audit_on else None
        if not found:
            raise ScanError(str(exc)) from exc
        policy_url, text = found
    paragraphs = segmenter.segment(text)
    host = urlsplit(policy_url).hostname or ""
    audit, audit_error = None, None
    if audit_on:
        try:
            audit = _audit(f"https://{host}/")
        except tracker_audit.AuditError as exc:
            audit_error = str(exc)
    return build_report(paragraphs, source="url", url=site_url, policy_url=policy_url, audit=audit, audit_error=audit_error)


def scan_text(text: str) -> dict:
    paragraphs = segmenter.segment(text)
    return build_report(paragraphs, source="text", url=None, policy_url=None, audit=None, audit_error=None)
