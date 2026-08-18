from fastapi.testclient import TestClient

from app.main import create_app


def test_health_tra_ve_trang_thai_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "file-understanding-api"
