"""SSRF-safe fetching plus policy-page discovery."""

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.ssrf import Resolver, SSRFError, default_resolver, validate_url

USER_AGENT = "PolicyScanBot/0.1 (+capstone project; respects robots.txt)"
COMMON_POLICY_PATHS = ("/privacy", "/privacy-policy", "/privacy-notice", "/legal/privacy", "/policies/privacy")
POLICY_LINK_WORDS = ("privacy policy", "privacy notice", "privacy statement", "privacy")


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    text: str


def safe_get(
    url: str,
    *,
    resolver: Resolver = default_resolver,
    transport: httpx.BaseTransport | None = None,
) -> FetchResult:
    """GET with SSRF validation before the request and after every redirect.

    The connection is pinned to the validated IP (Host header + SNI keep the real name),
    so DNS cannot change between validation and connect.
    """
    s = get_settings()
    current = url
    with httpx.Client(transport=transport, timeout=s.fetch_timeout_seconds, verify=True) as client:
        for _ in range(s.fetch_max_redirects + 1):
            try:
                target = validate_url(current, resolver)
            except SSRFError as exc:
                raise FetchError(f"blocked: {exc}") from exc
            parts = urlsplit(target.url)
            ip_host = f"[{target.ip}]" if ":" in target.ip else target.ip
            netloc = ip_host if parts.port is None else f"{ip_host}:{parts.port}"
            pinned = parts._replace(netloc=netloc).geturl()
            headers = {"Host": parts.netloc.rsplit("@", 1)[-1], "User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"}
            try:
                with client.stream(
                    "GET", pinned, headers=headers, follow_redirects=False,
                    extensions={"sni_hostname": target.host},
                ) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                        current = urljoin(target.url, resp.headers["location"])
                        continue
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > s.fetch_max_bytes:
                            raise FetchError("response too large")
                    ctype = resp.headers.get("content-type", "")
                    encoding = resp.encoding or "utf-8"
                    return FetchResult(target.url, resp.status_code, ctype, bytes(body).decode(encoding, "replace"))
            except httpx.HTTPError as exc:
                raise FetchError(f"request failed: {type(exc).__name__}") from exc
    raise FetchError("too many redirects")


def robots_allows(url: str, **kw) -> bool:
    parts = urlsplit(url)
    try:
        res = safe_get(f"{parts.scheme}://{parts.netloc}/robots.txt", **kw)
    except FetchError:
        return True  # no readable robots.txt
    if res.status != 200:
        return True
    rp = RobotFileParser()
    rp.parse(res.text.splitlines())
    return rp.can_fetch(USER_AGENT, url)


def find_policy_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return rank_policy_links([(a.get_text(" ", strip=True), a["href"]) for a in soup.find_all("a", href=True)], base_url)


def rank_policy_links(pairs: list[tuple[str, str]], base_url: str) -> list[str]:
    """pairs are (link text, href). Returns absolute URLs, best privacy-policy candidates first."""
    scored: list[tuple[int, str]] = []
    for link_text, href in pairs:
        text = link_text.lower()
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        for rank, word in enumerate(POLICY_LINK_WORDS):
            if word in text or word.replace(" ", "-") in href.lower():
                scored.append((rank, urljoin(base_url, href)))
                break
    seen, out = set(), []
    for _, link in sorted(scored, key=lambda x: x[0]):
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def fetch_policy(site_url: str, **kw) -> FetchResult:
    """Find and download the privacy policy page for a site."""
    if "://" not in site_url:
        site_url = "https://" + site_url
    try:
        home = safe_get(site_url, **kw)
    except FetchError:
        home = None
    candidates: list[str] = []
    if home and home.status == 200:
        candidates += find_policy_links(home.text, home.url)[:3]
    parts = urlsplit(home.url if home else site_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    candidates += [origin + p for p in COMMON_POLICY_PATHS]
    for cand in dict.fromkeys(candidates):
        if not robots_allows(cand, **kw):
            continue
        try:
            res = safe_get(cand, **kw)
        except FetchError:
            continue
        ctype = res.content_type.lower()
        if res.status == 200 and (not ctype or "html" in ctype or "text" in ctype) and len(res.text) > 500:
            return res
    raise FetchError("could not find a privacy policy page; paste the policy text instead")
