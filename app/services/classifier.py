"""Paragraph classifier into score categories.

Uses a trained scikit-learn model (models/<tag>/model.joblib, produced by ml/train_baseline.py)
when one is configured and present. Otherwise falls back to a transparent keyword classifier
so the app works before OPP-115 has been downloaded. Each result says which one produced it.
"""

import re
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

KEYWORDS: dict[str, re.Pattern] = {
    "collection": re.compile(r"\b(we collect|information (we|you) (collect|provide)|personal (data|information)|we (gather|receive|obtain)|cookies?)\b", re.IGNORECASE),
    "sharing": re.compile(r"\b(share|sell|disclose|third[- ]part(y|ies)|partners|affiliates|advertis)", re.IGNORECASE),
    "rights": re.compile(r"\b(your rights|right to|access|delete|erase|opt[- ]out|unsubscribe|correct|rectif|choices?)\b", re.IGNORECASE),
    "retention": re.compile(r"\b(retain|retention|store[sd]? (for|until)|as long as|delete after|keep (your )?(data|information))\b", re.IGNORECASE),
    "security": re.compile(r"\b(secur(e|ity)|encrypt|safeguard|protect (your|against)|unauthori[sz]ed)\b", re.IGNORECASE),
}


@lru_cache
def load_model(path: str):
    model_file = Path(path) / "model.joblib"
    if not model_file.exists():
        return None
    import joblib

    return joblib.load(model_file)  # trusted local artifact written by our own training script


def classify(paragraphs: list[str]) -> tuple[list[list[str]], str]:
    """Return (labels per paragraph, classifier name)."""
    bundle = load_model(get_settings().model_path)
    if bundle is not None:
        clf, vec, labels, thresholds = bundle["clf"], bundle["vec"], bundle["labels"], bundle["thresholds"]
        probs = clf.predict_proba(vec.transform(paragraphs))
        out = [[lab for lab, p, t in zip(labels, row, thresholds, strict=False) if p >= t] or ["informational"] for row in probs]
        return out, "ml"
    out = []
    for par in paragraphs:
        cats = [c for c, pat in KEYWORDS.items() if pat.search(par)]
        out.append(cats or ["informational"])
    return out, "keyword"
