"""Baseline classifier: TF-IDF + one-vs-rest Logistic Regression, split by policy.

Usage:  python -m ml.train_baseline [--data data/processed/opp115_paragraphs.csv] [--tag baseline-v0]

Splits 70/15/15 by policy (not paragraph) with a fixed seed, tunes a per-category threshold on
validation, reports per-category P/R/F1 plus micro/macro F1 on test, saves the model to
models/<tag>/ and writes docs/model-evaluation.md.
"""

import argparse
import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_recall_fscore_support

from ml.category_map import SCORE_CATEGORIES
from ml.model import OneVsRest

SEED = 42


def split_by_policy(df: pd.DataFrame, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    policies = np.array(sorted(df["policy_id"].unique()))
    rng = np.random.RandomState(seed)
    rng.shuffle(policies)
    n = len(policies)
    train_p, val_p, test_p = np.split(policies, [int(0.7 * n), int(0.85 * n)])
    return (df[df.policy_id.isin(train_p)], df[df.policy_id.isin(val_p)], df[df.policy_id.isin(test_p)])


def fit_models(X, Y, labels):
    models = {}
    for j, lab in enumerate(labels):
        if Y[:, j].sum() == 0:
            continue
        m = LogisticRegression(max_iter=1000, class_weight="balanced", C=4.0)
        m.fit(X, Y[:, j])
        models[lab] = m
    return models


def tune_thresholds(probs: np.ndarray, Y: np.ndarray) -> list[float]:
    out = []
    for j in range(Y.shape[1]):
        best_t, best_f = 0.5, -1.0
        for t in np.arange(0.2, 0.81, 0.05):
            f = f1_score(Y[:, j], probs[:, j] >= t, zero_division=0)
            if f > best_f:
                best_t, best_f = float(t), f
        out.append(round(best_t, 2))
    return out


def evaluate(Y, pred, labels) -> dict:
    p, r, f, s = precision_recall_fscore_support(Y, pred, zero_division=0)
    per = {l: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])} for i, l in enumerate(labels)}
    return {
        "per_category": per,
        "micro_f1": float(f1_score(Y, pred, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(Y, pred, average="macro", zero_division=0)),
    }


def write_report(metrics: dict, sizes: dict, tag: str, path: Path) -> None:
    lines = [
        "# Model evaluation",
        "",
        f"Generated {date.today()} by `python -m ml.train_baseline` (model tag `{tag}`).",
        "",
        "## Setup",
        "",
        "- Data: OPP-115 consolidated annotations (threshold 0.5), mapped to the six score categories plus *informational* (`ml/category_map.py`).",
        f"- Split by policy, seed {SEED}: {sizes['train_policies']} train / {sizes['val_policies']} validation / {sizes['test_policies']} test policies "
        f"({sizes['train']} / {sizes['val']} / {sizes['test']} paragraphs).",
        "- Model: TF-IDF (1-2 grams) + one-vs-rest Logistic Regression, balanced class weights, per-category thresholds tuned on validation.",
        "",
        "## Test results (baseline)",
        "",
        "| Category | Precision | Recall | F1 | Support |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cat, m in metrics["per_category"].items():
        lines.append(f"| {cat} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['support']} |")
    lines += [
        "",
        f"**Micro-F1: {metrics['micro_f1']:.3f}**  ·  **Macro-F1: {metrics['macro_f1']:.3f}**  (target micro-F1 >= 0.75)",
        "",
        "## DistilBERT",
        "",
        "Not yet run. Fine-tune with `ml/train_distilbert.py` (Colab GPU) and add its row here for the baseline-vs-DistilBERT comparison.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/processed/opp115_paragraphs.csv"))
    ap.add_argument("--tag", default="baseline-v0")
    ap.add_argument("--report", type=Path, default=Path("docs/model-evaluation.md"))
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    train, val, test = split_by_policy(df)
    labels = SCORE_CATEGORIES
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words="english")
    Xtr = vec.fit_transform(train.text)
    models = fit_models(Xtr, train[labels].values, labels)
    clf = OneVsRest(models, labels)
    thresholds = tune_thresholds(clf.predict_proba(vec.transform(val.text)), val[labels].values)
    probs = clf.predict_proba(vec.transform(test.text))
    pred = probs >= np.array(thresholds)
    metrics = evaluate(test[labels].values, pred, labels)

    out = Path("models") / args.tag
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({"clf": clf, "vec": vec, "labels": labels, "thresholds": thresholds}, out / "model.joblib")
    sizes = {
        "train": len(train), "val": len(val), "test": len(test),
        "train_policies": train.policy_id.nunique(), "val_policies": val.policy_id.nunique(), "test_policies": test.policy_id.nunique(),
    }
    (out / "metrics.json").write_text(json.dumps({"metrics": metrics, "thresholds": dict(zip(labels, thresholds, strict=False)), "sizes": sizes}, indent=2))
    write_report(metrics, sizes, args.tag, args.report)
    print(json.dumps({k: metrics[k] for k in ("micro_f1", "macro_f1")}))
    for cat, m in metrics["per_category"].items():
        print(f"  {cat:14s} P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f} n={m['support']}")


if __name__ == "__main__":
    main()
