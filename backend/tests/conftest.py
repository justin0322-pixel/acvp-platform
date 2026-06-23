import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # put backend/ on sys.path

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def acv_version() -> str:
    return get_settings().acv_version


@pytest.fixture
def auth_header(client) -> dict:
    s = get_settings()
    body = [{"acvVersion": s.acv_version}, {"password": s.demo_password}]
    token = client.post("/acvp/v1/login", json=body).json()[1]["accessToken"]
    return {"Authorization": f"Bearer {token}"}
