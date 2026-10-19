
import os
import uuid
import hashlib
from pathlib import Path

os.environ.setdefault(
    "CLOUDVAULT_SECRET_KEY",
    "local-testing-secret-key-do-not-use-in-production"
)

from fastapi.testclient import TestClient
from app.main import app
from app.storage_service import NODE1_DIR, NODE2_DIR


def test_upload_replicate_download_delete():
    unique = uuid.uuid4().hex
    username = f"filetest_{unique[:12]}"
    email = f"filetest_{unique[:12]}@example.com"
    password = "TestPassword123!"
    filename = f"cloudvault_test_{unique[:8]}.txt"
    content = b"CloudVault automated replication test."
    expected_hash = hashlib.sha256(content).hexdigest()

    with TestClient(app) as client:
        # 1. Create a dedicated test user.
        signup = client.post(
            "/api/auth/signup",
            json={
                "username": username,
                "email": email,
                "password": password,
            },
        )
        assert signup.status_code in (200, 201), signup.text

        # 2. Log in and obtain a token.
        login = client.post(
            "/api/auth/login",
            json={
                "username_or_email": email,
                "password": password,
            },
        )
        assert login.status_code == 200, login.text

        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Upload the test file.
        upload = client.post(
            "/api/files/upload",
            headers=headers,
            files={"file": (filename, content, "text/plain")},
        )
        assert upload.status_code in (200, 201), upload.text

        # 4. Find the uploaded record in the user's file list.
        listing = client.get("/api/files", headers=headers)
        assert listing.status_code == 200, listing.text

        payload = listing.json()
        records = payload if isinstance(payload, list) else payload.get("files", [])
        record = next(
            (item for item in records if item.get("filename") == filename),
            None,
        )
        assert record is not None, f"Uploaded file not found: {payload}"

        file_id = record.get("id", record.get("file_id"))
        stored_name = record.get("stored_name")

        # If the API doesn't expose stored_name, locate the new replica
        # by checking for a file whose content hash matches the test data.
        if not stored_name:
            candidates = []
            for directory in (NODE1_DIR, NODE2_DIR):
                for path in Path(directory).glob("*"):
                    if path.is_file():
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                        if digest == expected_hash:
                            candidates.append(path.name)

            assert candidates, "Could not find the uploaded file in either node."
            stored_name = candidates[0]

        node1_file = Path(NODE1_DIR) / stored_name
        node2_file = Path(NODE2_DIR) / stored_name

        try:
            # 5. Verify both replicas and their content.
            assert node1_file.is_file(), f"Missing replica: {node1_file}"
            assert node2_file.is_file(), f"Missing replica: {node2_file}"
            assert hashlib.sha256(node1_file.read_bytes()).hexdigest() == expected_hash
            assert hashlib.sha256(node2_file.read_bytes()).hexdigest() == expected_hash

            # 6. Download and verify the original content.
            assert file_id is not None, f"No file ID in record: {record}"
            download = client.get(
                f"/api/files/{file_id}/download",
                headers=headers,
            )
            assert download.status_code == 200, download.text
            assert download.content == content

            # 7. Delete only the file created by this test.
            deletion = client.delete(
                f"/api/files/{file_id}",
                headers=headers,
            )
            assert deletion.status_code in (200, 204), deletion.text

            # 8. Verify both copies have been removed.
            assert not node1_file.exists(), "Node 1 replica was not deleted."
            assert not node2_file.exists(), "Node 2 replica was not deleted."

        finally:
            # Clean up only this test's file if an assertion fails.
            node1_file.unlink(missing_ok=True)
            node2_file.unlink(missing_ok=True)
