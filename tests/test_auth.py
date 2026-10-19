
import email
import os
import uuid
from xmlrpc import client

os.environ.setdefault(
    "CLOUDVAULT_SECRET_KEY",
    "local-testing-secret-key-do-not-use-in-production"
)

from fastapi.testclient import TestClient
from app.main import app


def test_signup_and_login():
    # Use a unique email so repeated test runs do not collide.
    email = f"test_{uuid.uuid4().hex[:10]}@example.com"
    password = "TestPassword123!"

    with TestClient(app) as client:
        signup = client.post(
            "/api/auth/signup",
            json={
                "username": f"tester_{uuid.uuid4().hex[:8]}",
                "email": email,
                "password": password,
            },
        )

        assert signup.status_code in (200, 201), signup.text

         
        login = client.post(
            "/api/auth/login",
            json={
                "username_or_email": email,
                "password": password,
            },
        )


        assert login.status_code == 200, login.text
        data = login.json()
        assert data.get("access_token")
        assert data.get("token_type", "").lower() == "bearer"


def test_file_list_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/api/files")

    assert response.status_code == 401, response.text
