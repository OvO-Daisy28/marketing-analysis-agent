import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from marketing.config import settings
from marketing.db import Base, get_db, make_engine
from marketing.models import Dataset, ShoppingSession


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "model_mode", "mock")
    monkeypatch.setattr(settings, "max_steps", 20)
    monkeypatch.setattr(settings, "max_run_tokens", 80000)
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add(Dataset(id="fixture", source="synthetic-test-only", row_count=12))
        db.flush()
        for i in range(12):
            db.add(
                ShoppingSession(
                    dataset_id="fixture",
                    month="Nov" if i < 8 else "Dec",
                    traffic_type=1 if i < 3 else 2,
                    visitor_type="New_Visitor" if i % 2 else "Returning_Visitor",
                    region=1,
                    weekend=bool(i % 2),
                    purchased=i in {0, 3, 4, 8},
                )
            )
    yield factory
    engine.dispose()


@pytest.fixture
def client(factory, monkeypatch):
    import marketing.api as api
    from marketing.api import app, attempts

    attempts.clear()
    monkeypatch.setattr(api, "Session", factory)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def logged(client):
    body = {"username": "analyst", "password": "test-password-123"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    response = client.post("/api/auth/login", json=body)
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return client
