from pathlib import Path

from app.services import classifier, rules, scorer, segmenter, tracker_match
from app.services.scan import build_report, scan_text

FIX = Path(__file__).parent / "fixtures"
BAD = segmenter.segment(segmenter.html_to_text((FIX / "policy_bad.html").read_text()))
GOOD = segmenter.segment((FIX / "policy_good.txt").read_text())


def test_segmenter_strips_clutter_and_splits():
    joined = " ".join(BAD)
    assert "Copyright" not in joined
    assert len(BAD) >= 3


def test_segmenter_splits_long_paragraph():
    long = ("This is a sentence about data. " * 100).strip()
    assert all(len(p) <= 1300 for p in segmenter.segment(long))


def names(sigs):
    return {s.name for s in sigs}


def test_rules_bad_policy_signals():
    r = rules.run_rules(BAD)
    n = names(r["negatives"])
    assert {"location", "contacts", "browsing_history", "sells_data", "advertisers", "unnamed_partners", "indefinite_retention"} <= n
    assert r["hedge_count"] >= 4
    assert not r["positives"].get("encryption")


def test_rules_negation_not_flagged():
    r = rules.run_rules(["We do not sell your personal information to anyone, and we never collect your location data."])
    assert not names(r["negatives"])


def test_rules_good_policy_positives():
    r = rules.run_rules(GOOD)
    assert {"access_right", "deletion_right", "retention_period", "encryption", "safeguards"} <= set(r["positives"])
    assert "sells_data" not in names(r["negatives"])
    assert all(c["met"] for c in r["checklist"] if c["item"] in ("Right to access your data", "Opt out of sale / sharing"))


def test_quotes_are_exact_policy_sentences():
    r = rules.run_rules(BAD)
    sells = next(s for s in r["negatives"] if s.name == "sells_data")
    assert sells.sentence in " ".join(BAD)
    assert sells.source == "rules"


def test_keyword_classifier():
    labels, name = classifier.classify(["We encrypt all data in transit to protect against unauthorized access."])
    assert name == "keyword" and "security" in labels[0]


def test_scorer_bad_vs_good_text_only():
    bad = scorer.score_policy(rules.run_rules(BAD), None)
    good = scorer.score_policy(rules.run_rules(GOOD), None)
    assert bad["rating"] == "Poor" and bad["score"] < 5
    assert good["rating"] == "Good" and good["score"] >= 8
    pvp = next(c for c in bad["categories"] if c["key"] == "policy_vs_practice")
    assert pvp["checked"] is False and pvp["earned"] is None


def test_every_lost_point_has_a_reason():
    res = scorer.score_policy(rules.run_rules(BAD), None)
    for c in res["categories"]:
        lost = c["max"] - c["earned"] if c["checked"] else 0
        assert round(lost, 2) <= round(sum(r["points_lost"] for r in c["reasons"]), 2) + 1e-9
        assert (lost == 0) or c["reasons"]


def test_scorer_text_only_scaled_to_ten():
    res = scorer.score_policy({"negatives": [], "positives": {k: object() for k in
        ("access_right", "deletion_right", "retention_period", "encryption", "safeguards")}, "hedge_count": 0, "hedge_example": None}, None)
    assert res["score"] == 10.0


def test_scorer_undisclosed_trackers_cost_points():
    clean = {"negatives": [], "positives": {k: object() for k in
        ("access_right", "deletion_right", "retention_period", "encryption", "safeguards")}, "hedge_count": 0, "hedge_example": None}
    trackers = {"findings": [{"entity": "Meta", "category": "advertising", "disclosed": False},
                             {"entity": "Google", "category": "analytics", "disclosed": True}]}
    res = scorer.score_policy(clean, trackers)
    assert res["score"] == 9.5
    assert [r["source"] for r in res["reasons"]] == ["tracker audit"]


def test_score_floor_is_one():
    cats = {"location": "collection", "contacts": "collection", "biometrics": "collection", "health": "collection",
            "browsing_history": "collection", "sells_data": "sharing", "advertisers": "sharing",
            "unnamed_partners": "sharing", "indefinite_retention": "retention"}
    worst = {"negatives": [rules.Signal(c, n, "s") for n, c in cats.items()], "positives": {},
             "hedge_count": 99, "hedge_example": "x"}
    trackers = {"findings": [{"entity": str(i), "category": "advertising", "disclosed": False} for i in range(20)]}
    assert scorer.score_policy(worst, trackers)["score"] == 1.0


def test_tracker_matching_and_disclosure():
    hosts = {"www.google-analytics.com": "before", "connect.facebook.net": "after", "cdn.example.com": "before", "static.shop.com": "before"}
    out = tracker_match.compare_with_policy(hosts, "We use Google Analytics to count visits.", "shop.com")
    by = {f["entity"]: f for f in out["findings"]}
    assert by["Google"]["disclosed"] is True
    assert by["Meta"]["disclosed"] is False and by["Meta"]["phase"] == "after"
    assert len(out["findings"]) == 2  # first-party and unknown hosts ignored


def test_registrable_domain():
    assert tracker_match.registrable_domain("a.b.example.co.uk") == "example.co.uk"
    assert tracker_match.registrable_domain("www.example.com") == "example.com"


def test_build_report_with_audit_marks_policy_vs_practice():
    audit = {"site_host": "shop.com", "before": ["www.google-analytics.com", "connect.facebook.net"], "after": [], "cookies": 4, "banner_clicked": True}
    rep = build_report(GOOD, source="url", url="shop.com", policy_url="https://shop.com/privacy", audit=audit, audit_error=None)
    assert rep["trackers"]["checked"] is True
    assert any(f["entity"] == "Meta" and not f["disclosed"] for f in rep["trackers"]["findings"])
    assert "not legal advice" in rep["disclaimer"]
    pvp = next(c for c in rep["categories"] if c["key"] == "policy_vs_practice")
    assert pvp["checked"] and pvp["earned"] == 2.0  # Meta undisclosed: -0.5; Google is named in GOOD


def test_scan_text_too_short():
    import pytest

    from app.services.scan import ScanError

    with pytest.raises(ScanError):
        scan_text("too short")


def test_rules_scoped_by_classifier_labels():
    pars = ["We may sell your personal information to advertisers.", "Unrelated paragraph about how to contact us by mail."]
    unscoped = rules.run_rules(pars)
    assert "sells_data" in names(unscoped["negatives"])
    scoped = rules.run_rules(pars, [["informational"], ["informational"]])
    assert "sells_data" not in names(scoped["negatives"])
    scoped = rules.run_rules(pars, [["sharing"], ["informational"]])
    assert "sells_data" in names(scoped["negatives"])


def test_ml_model_loads_when_present(monkeypatch):
    from pathlib import Path as P

    import pytest

    from app.core.config import get_settings

    if not P("models/baseline-v0/model.joblib").exists():
        pytest.skip("baseline model not trained (python -m ml.load_opp115 && python -m ml.train_baseline)")
    monkeypatch.setenv("POLICYSCAN_MODEL_PATH", "models/baseline-v0")
    get_settings.cache_clear()
    classifier.load_model.cache_clear()
    labels, name = classifier.classify(["We will not sell your data. We share information with advertising partners."])
    assert name == "ml" and "sharing" in labels[0]
