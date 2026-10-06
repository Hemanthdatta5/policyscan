import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import limiter
from app.db import models
from app.services import classifier


@pytest.fixture(autouse=True)
def keyword_classifier_by_default(monkeypatch):
    """Tests must not depend on a locally trained (gitignored) model."""
    monkeypatch.setenv("POLICYSCAN_MODEL_PATH", "models/does-not-exist")
    get_settings.cache_clear()
    classifier.load_model.cache_clear()
    yield
    get_settings.cache_clear()
    classifier.load_model.cache_clear()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("POLICYSCAN_ENABLE_AUDIT", "false")
    get_settings.cache_clear()
    models.init_db("sqlite:///:memory:")
    limiter.reset()
    from app.main import app

    yield TestClient(app)  # no lifespan context: DB is initialised above
