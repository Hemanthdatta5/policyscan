"""Case study: scan popular sites and compare PolicyScan to ToS;DR grades.

Usage:  python -m ml.case_study [--out docs/case-study.md]   (needs network + Playwright)

Scans are polite: one site at a time with a pause between them; robots.txt is respected by
the fetcher. ToS;DR letter grades (A best .. E worst) are mapped to 5..1 for rank correlation.
"""

import argparse
import csv
import time
from datetime import date
from pathlib import Path

import httpx

from app.services.scan import ScanError, scan_url

SITES = [
    "google.com", "facebook.com", "x.com", "github.com", "reddit.com", "amazon.com", "netflix.com",
    "spotify.com", "duckduckgo.com", "microsoft.com", "apple.com", "linkedin.com", "pinterest.com",
    "tiktok.com", "dropbox.com", "mozilla.org", "proton.me", "zoom.us", "slack.com", "medium.com",
    "twitch.tv", "bbc.com", "theguardian.com", "nytimes.com", "stackoverflow.com", "ebay.com",
]
GRADE_VALUE = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
PAUSE_SECONDS = 3


def tosdr_grade(domain: str) -> str | None:
    try:
        r = httpx.get("https://api.tosdr.org/search/v5/", params={"query": domain}, timeout=20)
        services = r.json().get("services", [])
    except (httpx.HTTPError, ValueError):
        return None
    for s in services:
        if domain in s.get("urls", []) and s.get("rating") in GRADE_VALUE:
            return s["rating"]
    return None


def spearman(xs: list[float], ys: list[float]) -> float | None:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out, i = [0.0] * len(v), 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return out

    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("docs/case-study.md"))
    ap.add_argument("--csv", type=Path, default=Path("data/processed/case_study.csv"))
    args = ap.parse_args()

    rows = []
    for site in SITES:
        row = {"site": site, "score": "", "rating": "", "undisclosed_trackers": "", "tosdr": tosdr_grade(site) or "", "note": ""}
        try:
            rep = scan_url(site)
            row["score"], row["rating"] = rep["score"], rep["rating"]
            tr = rep["trackers"]
            row["undisclosed_trackers"] = sum(1 for f in tr["findings"] if not f["disclosed"]) if tr["checked"] else ""
            row["note"] = rep["policy_url"] if tr["checked"] else f"policy found; tracker audit unavailable ({tr['error']})"
        except ScanError as exc:
            row["note"] = f"not scanned: {exc}"
        rows.append(row)
        print(row, flush=True)
        time.sleep(PAUSE_SECONDS)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    both = [r for r in rows if r["score"] != "" and r["tosdr"]]
    rho = spearman([float(r["score"]) for r in both], [GRADE_VALUE[r["tosdr"]] for r in both])
    scanned = [r for r in rows if r["score"] != ""]
    lines = [
        "# Case study: PolicyScan vs. ToS;DR",
        "",
        f"Generated {date.today()} by `python -m ml.case_study`. Live scans, so results change as sites change.",
        "",
        f"- Sites attempted: {len(rows)}; scanned successfully: {len(scanned)}; with a ToS;DR grade as well: {len(both)}.",
        f"- Spearman rank correlation between PolicyScan score and ToS;DR grade (A=5 .. E=1): "
        + (f"**{rho:.2f}**" if rho is not None else "n/a (too few overlapping sites)") + ".",
        "",
        "| Site | PolicyScan score | Rating | Undisclosed trackers | ToS;DR | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(f"| {r['site']} | {r['score']} | {r['rating']} | {r['undisclosed_trackers']} | {r['tosdr'] or 'n/a'} | {r['note']} |")
    lines += [
        "",
        "## Reading this honestly",
        "",
        "- ToS;DR grades a service's terms and policies by community-reviewed points; PolicyScan scores one privacy policy plus the trackers loaded on the home page. They measure related but different things, so only a rough agreement is expected.",
        "- Sites that block automated requests, or whose policy is not on a discoverable page, are listed as not scanned rather than guessed.",
        "- Tracker results are for the home page only, before and after clicking a cookie banner button; deeper pages may load more.",
        "- Disclosure matching is by company name in the policy text, so a policy that only says \"advertising partners\" counts as not naming the tracker.",
        "",
    ]
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
