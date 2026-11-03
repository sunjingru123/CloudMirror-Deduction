"""健康检查接口测试。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    """在应用生命周期内提供测试客户端。"""
    with TestClient(app) as test_client:
        yield test_client


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["project_name"] == "云镜推演"
    assert data["project_name_en"] == "CloudMirror Deduction"
    assert data["version"]


def test_health_check_content_type(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_root_endpoint(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["docs"] == "/docs"
    assert data["health"] == "/api/health"
