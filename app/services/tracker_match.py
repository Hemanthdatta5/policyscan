"""Match third-party domains against tracker lists and compare with what the policy names.

Lists: a small vendored fallback (so tests and offline use work) plus an optional cached
EasyPrivacy file (.cache/easyprivacy.txt, fetched by update_easyprivacy()).
"""

import re
from pathlib import Path

import httpx

EASYPRIVACY_URL = "https://easylist.to/easylist/easyprivacy.txt"
EASYPRIVACY_CACHE = Path(".cache/easyprivacy.txt")

# domain -> (entity, category, aliases the policy might use to name them)
FALLBACK: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "google-analytics.com": ("Google", "analytics", ("google analytics", "google")),
    "googletagmanager.com": ("Google", "analytics", ("google tag manager", "google")),
    "doubleclick.net": ("Google", "advertising", ("doubleclick", "google")),
    "googlesyndication.com": ("Google", "advertising", ("adsense", "google")),
    "googleadservices.com": ("Google", "advertising", ("google ads", "google")),
    "facebook.net": ("Meta", "advertising", ("facebook", "meta")),
    "facebook.com": ("Meta", "advertising", ("facebook", "meta")),
    "connect.facebook.net": ("Meta", "advertising", ("facebook", "meta")),
    "fbcdn.net": ("Meta", "advertising", ("facebook", "meta")),
    "twitter.com": ("X (Twitter)", "advertising", ("twitter", "x corp")),
    "ads-twitter.com": ("X (Twitter)", "advertising", ("twitter", "x corp")),
    "linkedin.com": ("LinkedIn", "advertising", ("linkedin",)),
    "licdn.com": ("LinkedIn", "advertising", ("linkedin",)),
    "snap.licdn.com": ("LinkedIn", "advertising", ("linkedin",)),
    "tiktok.com": ("TikTok", "advertising", ("tiktok",)),
    "analytics.tiktok.com": ("TikTok", "advertising", ("tiktok",)),
    "pinterest.com": ("Pinterest", "advertising", ("pinterest",)),
    "hotjar.com": ("Hotjar", "session recording", ("hotjar",)),
    "fullstory.com": ("FullStory", "session recording", ("fullstory",)),
    "mouseflow.com": ("Mouseflow", "session recording", ("mouseflow",)),
    "clarity.ms": ("Microsoft", "session recording", ("clarity", "microsoft")),
    "bing.com": ("Microsoft", "advertising", ("bing", "microsoft")),
    "segment.io": ("Segment", "analytics", ("segment",)),
    "segment.com": ("Segment", "analytics", ("segment",)),
    "mixpanel.com": ("Mixpanel", "analytics", ("mixpanel",)),
    "amplitude.com": ("Amplitude", "analytics", ("amplitude",)),
    "heap.io": ("Heap", "analytics", ("heap",)),
    "heapanalytics.com": ("Heap", "analytics", ("heap",)),
    "optimizely.com": ("Optimizely", "analytics", ("optimizely",)),
    "scorecardresearch.com": ("Comscore", "analytics", ("comscore", "scorecard")),
    "quantserve.com": ("Quantcast", "advertising", ("quantcast",)),
    "criteo.com": ("Criteo", "advertising", ("criteo",)),
    "criteo.net": ("Criteo", "advertising", ("criteo",)),
    "taboola.com": ("Taboola", "advertising", ("taboola",)),
    "outbrain.com": ("Outbrain", "advertising", ("outbrain",)),
    "adnxs.com": ("Xandr (Microsoft)", "advertising", ("xandr", "appnexus")),
    "rubiconproject.com": ("Magnite", "advertising", ("rubicon", "magnite")),
    "pubmatic.com": ("PubMatic", "advertising", ("pubmatic",)),
    "amazon-adsystem.com": ("Amazon", "advertising", ("amazon",)),
    "demdex.net": ("Adobe", "advertising", ("adobe", "demdex")),
    "omtrdc.net": ("Adobe", "analytics", ("adobe", "omniture")),
    "newrelic.com": ("New Relic", "analytics", ("new relic",)),
    "nr-data.net": ("New Relic", "analytics", ("new relic",)),
    "sentry.io": ("Sentry", "analytics", ("sentry",)),
    "hubspot.com": ("HubSpot", "marketing", ("hubspot",)),
    "hs-analytics.net": ("HubSpot", "analytics", ("hubspot",)),
    "marketo.net": ("Marketo", "marketing", ("marketo", "adobe")),
    "yandex.ru": ("Yandex", "analytics", ("yandex",)),
    "mc.yandex.ru": ("Yandex", "analytics", ("yandex",)),
}

_TWO_PART_TLDS = {"co.uk", "org.uk", "com.au", "co.jp", "co.in", "com.br", "co.nz", "com.cn"}


def registrable_domain(host: str) -> str:
    host = host.lower().rstrip(".")
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _TWO_PART_TLDS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_third_party(request_host: str, site_host: str) -> bool:
    return registrable_domain(request_host) != registrable_domain(site_host)


def _load_easyprivacy() -> set[str]:
    if not EASYPRIVACY_CACHE.exists():
        return set()
    domains = set()
    for line in EASYPRIVACY_CACHE.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^\|\|([a-z0-9.-]+)\^(\$.*)?$", line.strip())
        if m and "/" not in m.group(1):
            domains.add(m.group(1))
    return domains


def update_easyprivacy() -> int:
    """Download EasyPrivacy into the local cache. Returns the number of domain rules."""
    resp = httpx.get(EASYPRIVACY_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    EASYPRIVACY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    EASYPRIVACY_CACHE.write_text(resp.text, encoding="utf-8")
    return len(_load_easyprivacy())


def lookup(host: str, easyprivacy: set[str] | None = None) -> tuple[str, str, tuple[str, ...]] | None:
    host = host.lower().rstrip(".")
    parts = host.split(".")
    for i in range(len(parts) - 1):
        suffix = ".".join(parts[i:])
        if suffix in FALLBACK:
            return FALLBACK[suffix]
    ep = easyprivacy if easyprivacy is not None else _load_easyprivacy()
    for i in range(len(parts) - 1):
        suffix = ".".join(parts[i:])
        if suffix in ep:
            reg = registrable_domain(host)
            return (reg, "tracking (EasyPrivacy)", (reg, reg.split(".")[0]))
    return None


def compare_with_policy(hosts: dict[str, str], policy_text: str, site_host: str) -> dict:
    """hosts maps third-party host -> phase ('before' or 'after' the cookie banner)."""
    text = policy_text.lower()
    by_entity: dict[str, dict] = {}
    ep = _load_easyprivacy()
    for host, phase in sorted(hosts.items()):
        if not is_third_party(host, site_host):
            continue
        hit = lookup(host, ep)
        if not hit:
            continue
        entity, category, aliases = hit
        disclosed = any(a in text for a in (*aliases, entity.lower()))
        f = by_entity.setdefault(
            entity, {"entity": entity, "category": category, "domains": [], "disclosed": disclosed, "phase": phase}
        )
        f["domains"].append(host)
        if phase == "before":
            f["phase"] = "before"
    return {"findings": list(by_entity.values())}
