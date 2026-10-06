"""Turn the OPP-115 consolidated annotations into a paragraph-level multi-label CSV.

Usage:  python -m ml.load_opp115 [--root data/raw/OPP-115] [--out data/processed/opp115_paragraphs.csv]

One row per policy segment (paragraph): policy_id, segment_id, text, then one 0/1 column per
score category (see ml/category_map.py). Segments with no annotation are 'informational'.
"""

import argparse
import csv
import re
from pathlib import Path

from ml.category_map import OPP115_TO_SCORE_CATEGORY, SCORE_CATEGORIES

CONSOLIDATION_DIR = "consolidation/threshold-0.5-overlap-similarity"
MIN_CHARS = 20


def clean(segment: str) -> str:
    segment = re.sub(r"<br\s*/?>", " ", segment, flags=re.IGNORECASE)
    segment = re.sub(r"<[^>]+>", " ", segment)
    return re.sub(r"\s+", " ", segment).strip()


def load_policy(root: Path, stem: str) -> list[dict]:
    policy_html = (root / "sanitized_policies" / f"{stem}.html").read_text(encoding="utf-8", errors="ignore")
    segments = [clean(s) for s in policy_html.split("|||")]
    labels: dict[int, set[str]] = {}
    with open(root / CONSOLIDATION_DIR / f"{stem}.csv", newline="", encoding="utf-8", errors="ignore") as f:
        for row in csv.reader(f):
            if len(row) < 6:
                continue
            try:
                seg_id = int(row[4])
            except ValueError:
                continue
            cat = OPP115_TO_SCORE_CATEGORY.get(row[5])
            if cat:
                labels.setdefault(seg_id, set()).add(cat)
    rows = []
    for i, text in enumerate(segments):
        if len(text) < MIN_CHARS:
            continue
        cats = labels.get(i) or {"informational"}
        rows.append({"policy_id": stem, "segment_id": i, "text": text, **{c: int(c in cats) for c in SCORE_CATEGORIES}})
    return rows


def build_dataset(root: Path, out: Path) -> int:
    stems = sorted(p.stem for p in (root / CONSOLIDATION_DIR).glob("*.csv"))
    if not stems:
        raise SystemExit(f"No OPP-115 annotations found under {root / CONSOLIDATION_DIR}. Download the corpus to data/raw/.")
    rows = [r for stem in stems for r in load_policy(root, stem)]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["policy_id", "segment_id", "text", *SCORE_CATEGORIES])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data/raw/OPP-115"))
    ap.add_argument("--out", type=Path, default=Path("data/processed/opp115_paragraphs.csv"))
    args = ap.parse_args()
    print(f"Wrote {build_dataset(args.root, args.out)} paragraphs to {args.out}")
