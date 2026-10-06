"""Scoring weights and rating bands. Single source of truth; must match the proposal.

Edit here to tune the score. The scorer imports these values and never hard-codes them.
"""

CATEGORY_POINTS: dict[str, float] = {
    "collection": 2.0,
    "sharing": 2.0,
    "rights": 1.5,
    "retention": 1.0,
    "security": 1.0,
    "policy_vs_practice": 2.5,
}

TOTAL_POINTS = sum(CATEGORY_POINTS.values())  # 10.0

# (minimum score, label), checked top to bottom
RATING_BANDS: list[tuple[float, str]] = [
    (8.0, "Good"),
    (5.0, "Fair"),
    (0.0, "Poor"),
]

CATEGORY_LABELS: dict[str, str] = {
    "collection": "Data collection",
    "sharing": "Data sharing",
    "rights": "User rights",
    "retention": "Data retention",
    "security": "Security & clarity",
    "policy_vs_practice": "Policy vs. practice",
}

# Points lost per signal. Each category's penalties are capped at its CATEGORY_POINTS.
PENALTIES: dict[str, float] = {
    "location": 0.5,
    "contacts": 0.5,
    "biometrics": 0.5,
    "health": 0.5,
    "browsing_history": 0.5,
    "sells_data": 1.0,
    "advertisers": 0.5,
    "unnamed_partners": 0.5,
    "no_access_right": 0.75,
    "no_deletion_right": 0.75,
    "indefinite_retention": 1.0,
    "indefinite_with_period": 0.5,
    "no_retention_period": 1.0,
    "no_encryption": 0.4,
    "no_safeguards": 0.2,
    "hedge_some": 0.2,  # 1-5 hedge words
    "hedge_many": 0.4,  # more than HEDGE_MANY_THRESHOLD
    "undisclosed_tracker": 0.5,  # per tracker company the policy never names
}
HEDGE_MANY_THRESHOLD = 5

# The displayed score never drops below this.
MIN_SCORE = 1.0

# Hedge words that cost points in the Security & clarity category
HEDGE_WORDS: tuple[str, ...] = ("may", "certain", "from time to time")

if abs(TOTAL_POINTS - 10.0) > 1e-9:
    raise RuntimeError("Category points must sum to 10")
