"""Rules layer: sub-signals inside a category, found with patterns over policy paragraphs.

Every Signal records the exact sentence that triggered it and says it came from the rules
layer, so the report can show which layer produced each flag.
"""

import re
from dataclasses import dataclass

from app.core.scoring_config import HEDGE_WORDS

NEGATION = re.compile(r"\b(do not|does not|don't|doesn't|never|will not|won't|not|no)\b[^.]{0,80}$", re.IGNORECASE)
_SENT_SPLIT = re.compile(r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bInc\.)(?<=[.!?])\s+(?=[A-Z\"'(])")


@dataclass(frozen=True)
class Signal:
    category: str  # scoring category
    name: str
    sentence: str
    source: str = "rules"


def _sentences(par: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(par) if s.strip()]


def _pat(*words: str) -> re.Pattern:
    return re.compile("|".join(words), re.IGNORECASE)


# (category, signal name, pattern, negatable)
_COLLECT = r"(collect|gather|track|record|log|store|obtain|receive|process|use)(s|ed|ing)?\b"
NEGATIVE_RULES: list[tuple[str, str, re.Pattern, bool]] = [
    ("collection", "location", _pat(rf"\b{_COLLECT}[^.]{{0,80}}\b(precise |exact |gps |geo)?location (data|information)", rf"\b{_COLLECT}[^.]{{0,80}}\bgeolocation\b", rf"\b{_COLLECT}[^.]{{0,40}}\bgps\b"), True),
    ("collection", "contacts", _pat(r"\b(address book|contact list|your contacts|phone contacts)\b"), True),
    ("collection", "biometrics", _pat(r"\bbiometric", r"\bfingerprint", r"\bfacial recognition", r"\bvoiceprint"), True),
    ("collection", "health", _pat(rf"\b{_COLLECT}[^.]{{0,60}}\b(health|medical) (data|information|records)"), True),
    ("collection", "browsing_history", _pat(rf"\b{_COLLECT}[^.]{{0,80}}\b(browsing|search) (history|behaviou?r|activity)", rf"\b{_COLLECT}[^.]{{0,60}}\bwebsites? (you )?visit(ed)?\b"), True),
    ("sharing", "sells_data", _pat(r"\bwe\s+(may\s+|also\s+|do\s+|will\s+)*(sell|rent|trade)\b[^.]{0,60}\b(data|information)", r"\b(data|information)\b[^.]{0,40}\b(is|are|may be|will be)\s+sold\b"), True),
    ("sharing", "advertisers", _pat(r"\b(share|disclose|sell)[^.]{0,80}\badvertis(er|ers|ing partners?|ing networks?|ing companies)", r"\badvertising partners?\b"), True),
    ("sharing", "unnamed_partners", _pat(r"\b(share|disclose|provide|send|transfer)[^.]{0,80}\b(partners|affiliates|third[- ]part(y|ies))\b"), True),
    ("retention", "indefinite_retention", _pat(r"as long as (is )?(necessary|needed|required)", r"\bindefinitely\b", r"\bfor as long as\b"), False),
]

POSITIVE_RULES: list[tuple[str, str, re.Pattern]] = [
    ("rights", "access_right", _pat(r"\b(access|obtain a copy|request a copy)\b[^.]{0,60}\b(your )?(personal )?(data|information)", r"right to access")),
    ("rights", "deletion_right", _pat(r"\b(delete|erase|erasure|remove)\b[^.]{0,60}\b(your )?(personal )?(data|information|account)", r"right to (delete|erasure)")),
    ("retention", "retention_period", _pat(r"\b(for|within|after|up to)\s+(\d+|one|two|three|six|twelve|thirty|ninety)\s*(\(\d+\)\s*)?(days?|weeks?|months?|years?)\b", r"\bretain[^.]{0,60}\b\d+\s*(days?|months?|years?)")),
    ("security", "encryption", _pat(r"\bencrypt(ed|ion)?\b", r"\bTLS\b", r"\bSSL\b", r"\bHTTPS\b")),
    ("security", "safeguards", _pat(r"\b(security (measures|safeguards|controls)|access controls?|firewalls?|two-factor|multi-factor|security audits?|penetration test)")),
]

HEDGE_PATTERNS = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in HEDGE_WORDS]

CHECKLIST: list[tuple[str, str, re.Pattern]] = [
    ("GDPR", "Right to access your data", _pat(r"right to access", r"access (to )?your (personal )?(data|information)", r"copy of your (personal )?(data|information)")),
    ("GDPR", "Right to erasure / deletion", _pat(r"right to (erasure|delete)", r"delete your (personal )?(data|information|account)", r"request (the )?deletion")),
    ("GDPR", "Right to withdraw consent", _pat(r"withdraw (your )?consent")),
    ("GDPR", "Legal basis for processing stated", _pat(r"legal basis", r"legitimate interests?", r"lawful basis")),
    ("GDPR", "Data protection officer / contact", _pat(r"data protection officer", r"\bDPO\b", r"privacy@", r"contact us")),
    ("GDPR", "Data transfers outside the EU explained", _pat(r"international transfer", r"standard contractual clauses", r"transfer(red)? (your )?(data|information) (to|outside)")),
    ("CCPA", "Right to know what is collected", _pat(r"right to know", r"categories of personal information")),
    ("CCPA", "Right to delete", _pat(r"right to delete", r"request (that we )?delete")),
    ("CCPA", "Opt out of sale / sharing", _pat(r"do not sell", r"opt[- ]out of (the )?(sale|sharing)", r"not sell or share")),
    ("CCPA", "Non-discrimination for exercising rights", _pat(r"non-?discriminat", r"will not discriminate")),
]


def _find(par: str, pattern: re.Pattern, negatable: bool) -> str | None:
    for sent in _sentences(par):
        m = pattern.search(sent)
        if not m:
            continue
        if negatable and NEGATION.search(sent[: m.start()]):
            continue
        return sent
    return None


def run_rules(paragraphs: list[str], labels: list[list[str]] | None = None) -> dict:
    """Return negative signals, positive signals, hedge count and the GDPR/CCPA checklist.

    `labels` are the classifier's categories per paragraph. When given, a negative rule only
    looks at paragraphs the classifier assigned to that rule's category (classifier finds the
    category, rules find the sub-signal). Positive rules look everywhere so that a missed
    paragraph cannot cost points for a right or safeguard the policy does state.
    """
    negatives: list[Signal] = []
    positives: dict[str, Signal] = {}
    for i, par in enumerate(paragraphs):
        for cat, name, pat, negatable in NEGATIVE_RULES:
            if labels is not None and cat not in labels[i]:
                continue
            sent = _find(par, pat, negatable)
            if sent and not any(s.name == name for s in negatives):
                negatives.append(Signal(cat, name, sent))
        for cat, name, pat in POSITIVE_RULES:
            sent = _find(par, pat, False)
            if sent and name not in positives:
                positives[name] = Signal(cat, name, sent)

    text = " ".join(paragraphs)
    hedges = [(w, len(p.findall(text))) for w, p in zip(HEDGE_WORDS, HEDGE_PATTERNS, strict=False)]
    hedge_example = next(
        (s for par in paragraphs for s in _sentences(par) if any(p.search(s) for p in HEDGE_PATTERNS)), None
    )
    checklist = [
        {"regime": reg, "item": item, "met": bool(pat.search(text))} for reg, item, pat in CHECKLIST
    ]
    return {
        "negatives": negatives,
        "positives": positives,
        "hedge_count": sum(n for _, n in hedges),
        "hedge_example": hedge_example,
        "checklist": checklist,
    }
