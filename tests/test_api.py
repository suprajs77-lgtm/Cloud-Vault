
import os

os.environ.setdefault(
    "CLOUDVAULT_SECRET_KEY",
    "local-testing-secret-key-do-not-use-in-production"
)

from fastapi.testclient import TestClient
from app.main import app


def test_root_endpoint():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    data = response.json()

    assert data["project"] == "CloudVault"
    assert data["status"] == "running"


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["api"] == "healthy"
    assert data["database"] == "connected"

    storage = data["storage"]
    assert storage["files_directory_exists"] is True
    assert storage["versions_directory_exists"] is True
    assert storage["node1_exists"] is True
    assert storage["node2_exists"] is True
