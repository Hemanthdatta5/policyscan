"""Model wrapper kept in its own module so saved models unpickle as ml.model.OneVsRest."""

import numpy as np


class OneVsRest:
    """Exposes predict_proba over all labels from one binary model per label."""

    def __init__(self, models: dict, labels: list[str]):
        self.models, self.labels = models, labels

    def predict_proba(self, X):
        cols = [
            self.models[lab].predict_proba(X)[:, 1] if lab in self.models else np.zeros(X.shape[0])
            for lab in self.labels
        ]
        return np.column_stack(cols)
