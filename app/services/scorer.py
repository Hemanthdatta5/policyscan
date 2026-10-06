"""Pure scorer: rule signals + tracker comparison in, score + reasons out. No I/O."""

from app.core.scoring_config import (
    CATEGORY_LABELS,
    CATEGORY_POINTS,
    HEDGE_MANY_THRESHOLD,
    MIN_SCORE,
    PENALTIES,
    RATING_BANDS,
    TOTAL_POINTS,
)

QUOTE_MAX = 400

SIGNAL_REASONS = {
    "location": "Policy says it collects location data.",
    "contacts": "Policy says it collects your contacts.",
    "biometrics": "Policy says it collects biometric data.",
    "health": "Policy says it collects health data.",
    "browsing_history": "Policy says it collects browsing history or activity.",
    "sells_data": "Policy says data is sold.",
    "advertisers": "Policy says data is shared with advertisers or advertising partners.",
    "unnamed_partners": "Policy shares data with partners, affiliates or third parties without naming them.",
    "indefinite_retention": 'Policy keeps data "as long as necessary" or indefinitely instead of a fixed time.',
}


def rating_for(score: float) -> str:
    for minimum, label in RATING_BANDS:
        if score >= minimum:
            return label
    return RATING_BANDS[-1][1]


def _reason(category: str, points: float, text: str, quote: str | None, source: str) -> dict:
    if quote and len(quote) > QUOTE_MAX:
        quote = quote[: QUOTE_MAX - 1].rstrip() + "…"
    return {"category": category, "points_lost": round(points, 2), "reason": text, "quote": quote, "source": source}


def score_policy(rules: dict, trackers: dict | None) -> dict:
    """`rules` comes from rules.run_rules; `trackers` is None for pasted text (not checked),
    else {"findings": [{"entity","domains","category","disclosed"}, ...]}."""
    reasons: list[dict] = []
    neg = {s.name: s for s in rules["negatives"]}
    pos = rules["positives"]

    # Data collection
    for name in ("location", "contacts", "biometrics", "health", "browsing_history"):
        if name in neg:
            reasons.append(_reason("collection", PENALTIES[name], SIGNAL_REASONS[name], neg[name].sentence, neg[name].source))

    # Data sharing
    for name in ("sells_data", "advertisers", "unnamed_partners"):
        if name in neg:
            reasons.append(_reason("sharing", PENALTIES[name], SIGNAL_REASONS[name], neg[name].sentence, neg[name].source))

    # User rights
    if "access_right" not in pos:
        reasons.append(_reason("rights", PENALTIES["no_access_right"], "Policy does not say you can access your data.", None, "rules"))
    if "deletion_right" not in pos:
        reasons.append(_reason("rights", PENALTIES["no_deletion_right"], "Policy does not say you can delete your data.", None, "rules"))

    # Data retention
    has_period = "retention_period" in pos
    if "indefinite_retention" in neg:
        s = neg["indefinite_retention"]
        pts = PENALTIES["indefinite_with_period"] if has_period else PENALTIES["indefinite_retention"]
        reasons.append(_reason("retention", pts, SIGNAL_REASONS["indefinite_retention"], s.sentence, s.source))
    elif not has_period:
        reasons.append(_reason("retention", PENALTIES["no_retention_period"], "Policy states no time limit for keeping data.", None, "rules"))

    # Security & clarity
    if "encryption" not in pos:
        reasons.append(_reason("security", PENALTIES["no_encryption"], "Policy does not mention encryption.", None, "rules"))
    if "safeguards" not in pos:
        reasons.append(_reason("security", PENALTIES["no_safeguards"], "Policy describes no concrete safeguards.", None, "rules"))
    hedges = rules["hedge_count"]
    if hedges:
        pts = PENALTIES["hedge_many"] if hedges > HEDGE_MANY_THRESHOLD else PENALTIES["hedge_some"]
        reasons.append(_reason("security", pts, f"Vague hedge words (\"may\", \"certain\", \"from time to time\") appear {hedges} times.", rules["hedge_example"], "rules"))

    # Policy vs. practice
    checked_pvp = trackers is not None
    if checked_pvp:
        for f in trackers["findings"]:
            if not f["disclosed"]:
                reasons.append(_reason(
                    "policy_vs_practice", PENALTIES["undisclosed_tracker"],
                    f"Site loads {f['entity']} ({f['category']}) trackers that the policy never mentions.",
                    None, "tracker audit",
                ))

    categories, earned_total, max_total = [], 0.0, 0.0
    for key, max_pts in CATEGORY_POINTS.items():
        checked = key != "policy_vs_practice" or checked_pvp
        cat_reasons = [r for r in reasons if r["category"] == key]
        lost = min(max_pts, sum(r["points_lost"] for r in cat_reasons))
        earned = max_pts - lost if checked else None
        if checked:
            earned_total += earned
            max_total += max_pts
        categories.append({
            "key": key, "label": CATEGORY_LABELS[key], "max": max_pts,
            "earned": None if earned is None else round(earned, 2),
            "checked": checked, "reasons": cat_reasons,
        })

    scaled = earned_total / max_total * TOTAL_POINTS if max_total else 0.0
    score = round(max(MIN_SCORE, min(TOTAL_POINTS, scaled)), 1)
    return {"score": score, "rating": rating_for(score), "categories": categories, "reasons": reasons}
