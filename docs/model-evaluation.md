# Model evaluation

Generated 2026-10-05 by `python -m ml.train_baseline` (model tag `baseline-v0`).

## Setup

- Data: OPP-115 consolidated annotations (threshold 0.5), mapped to the six score categories plus *informational* (`ml/category_map.py`).
- Split by policy, seed 42: 80 train / 17 validation / 18 test policies (2789 / 445 / 535 paragraphs).
- Model: TF-IDF (1-2 grams) + one-vs-rest Logistic Regression, balanced class weights, per-category thresholds tuned on validation.

## Test results (baseline)

| Category | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- |
| collection | 0.87 | 0.85 | 0.86 | 219 |
| sharing | 0.82 | 0.83 | 0.83 | 132 |
| rights | 0.71 | 0.57 | 0.63 | 90 |
| retention | 0.58 | 0.41 | 0.48 | 27 |
| security | 0.91 | 0.58 | 0.71 | 67 |
| informational | 0.86 | 0.73 | 0.79 | 303 |

**Micro-F1: 0.785**  ·  **Macro-F1: 0.716**  (target micro-F1 >= 0.75)

## DistilBERT

Not yet run. Fine-tune with `ml/train_distilbert.py` (Colab GPU) and add its row here for the baseline-vs-DistilBERT comparison.
