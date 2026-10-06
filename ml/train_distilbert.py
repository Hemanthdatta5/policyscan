"""Fine-tune DistilBERT for multi-label policy paragraph classification.

Colab (free GPU):   !pip install -q transformers torch pandas scikit-learn
                    !python -m ml.train_distilbert --epochs 4
CPU smoke test:     python -m ml.train_distilbert --smoke      (tiny subset, 1 epoch, ~minutes)

Uses the same policy-level 70/15/15 split and seed as the baseline so numbers are comparable.
Saves to models/<tag>/ (HF format + thresholds.json) and prints per-category P/R/F1.
Requires: pip install -e ".[ml,transformers]"
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, precision_recall_fscore_support
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ml.category_map import SCORE_CATEGORIES
from ml.train_baseline import SEED, split_by_policy, tune_thresholds

BASE_MODEL = "distilbert-base-uncased"
MAX_LEN = 256


class ParagraphDataset(Dataset):
    def __init__(self, df: pd.DataFrame, tok):
        self.enc = tok(list(df.text), truncation=True, max_length=MAX_LEN, padding="max_length", return_tensors="pt")
        self.y = torch.tensor(df[SCORE_CATEGORIES].values, dtype=torch.float)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, i):
        return {k: v[i] for k, v in self.enc.items()}, self.y[i]


def predict_probs(model, loader, device) -> np.ndarray:
    model.eval()
    out = []
    with torch.no_grad():
        for x, _ in loader:
            logits = model(**{k: v.to(device) for k, v in x.items()}).logits
            out.append(torch.sigmoid(logits).cpu().numpy())
    return np.vstack(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/processed/opp115_paragraphs.csv"))
    ap.add_argument("--tag", default="distilbert-v0")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--smoke", action="store_true", help="tiny subset, 1 epoch, for CPU smoke tests")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    df = pd.read_csv(args.data)
    train, val, test = split_by_policy(df)
    if args.smoke:
        train, val, test = train.head(64), val.head(32), test.head(32)
        args.epochs, args.batch_size = 1, 8

    # Training-only script; the base model is a public Hugging Face checkpoint. Pin a revision for releases.
    tok = AutoTokenizer.from_pretrained(BASE_MODEL)  # nosec B615
    model = AutoModelForSequenceClassification.from_pretrained(  # nosec B615
        BASE_MODEL, num_labels=len(SCORE_CATEGORIES), problem_type="multi_label_classification"
    ).to(device)

    loaders = {n: DataLoader(ParagraphDataset(d, tok), batch_size=args.batch_size, shuffle=(n == "train"))
               for n, d in (("train", train), ("val", val), ("test", test))}
    pos = train[SCORE_CATEGORIES].values.sum(axis=0).clip(min=1)
    pos_weight = torch.tensor((len(train) - pos) / pos, dtype=torch.float).clamp(max=10).to(device)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)  # class imbalance
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    for epoch in range(args.epochs):
        model.train()
        total = 0.0
        for x, y in loaders["train"]:
            opt.zero_grad()
            logits = model(**{k: v.to(device) for k, v in x.items()}).logits
            loss = loss_fn(logits, y.to(device))
            loss.backward()
            opt.step()
            total += loss.item()
        print(f"epoch {epoch + 1}/{args.epochs} loss={total / len(loaders['train']):.4f}")

    thresholds = tune_thresholds(predict_probs(model, loaders["val"], device), val[SCORE_CATEGORIES].values)
    Y = test[SCORE_CATEGORIES].values
    pred = predict_probs(model, loaders["test"], device) >= np.array(thresholds)
    p, r, f, s = precision_recall_fscore_support(Y, pred, zero_division=0)
    for i, cat in enumerate(SCORE_CATEGORIES):
        print(f"  {cat:14s} P={p[i]:.2f} R={r[i]:.2f} F1={f[i]:.2f} n={int(s[i])}")
    micro = f1_score(Y, pred, average="micro", zero_division=0)
    macro = f1_score(Y, pred, average="macro", zero_division=0)
    print(json.dumps({"micro_f1": micro, "macro_f1": macro}))

    out = Path("models") / args.tag
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    (out / "thresholds.json").write_text(json.dumps(dict(zip(SCORE_CATEGORIES, thresholds, strict=False))))


if __name__ == "__main__":
    main()
