
import hashlib
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from pwdlib import PasswordHash
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.database import get_connection, init_db
from app.storage_service import (
    STORAGE_DIR,
    NODE1_DIR,
    NODE2_DIR,
    calculate_sha256,
    delete_replicas,
    get_storage_info,
    store_replicated_file,
)


MAX_FILE_SIZE = 20 * 1024 * 1024
ALGORITHM = "HS256"

SECRET_KEY = os.environ.get("CLOUDVAULT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "Set CLOUDVAULT_SECRET_KEY before starting CloudVault."
    )

password_hasher = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    NODE1_DIR.mkdir(parents=True, exist_ok=True)
    NODE2_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="CloudVault API",
    description="Authenticated file storage with replicated copies",
    version="2.0.0",
)

app.router.lifespan_context = lifespan

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------- AUTHENTICATION ----------------

class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username_or_email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with get_connection() as connection:
        user = connection.execute(
            """
            SELECT id, username, email
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User account not found.",
        )

    return dict(user)


@app.post("/api/auth/signup", status_code=201)
def signup(data: SignupRequest):
    username = data.username.strip()
    email = data.email.strip().lower()

    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
        raise HTTPException(
            status_code=400,
            detail="Username must contain 3-30 letters, numbers, dots, underscores, or hyphens.",
        )

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email address.",
        )

    password_hash = password_hasher.hash(data.password)

    with get_connection() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
                """,
                (username, email, password_hash),
            )
            connection.commit()
            user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="Username or email is already registered.",
            )

    return {
        "message": "Account created successfully",
        "user": {
            "id": user_id,
            "username": username,
            "email": email,
        },
    }


@app.post("/api/auth/login")
def login(data: LoginRequest):
    identifier = data.username_or_email.strip()

    with get_connection() as connection:
        user = connection.execute(
            """
            SELECT id, username, email, password_hash
            FROM users
            WHERE username = ? COLLATE NOCASE
               OR email = ? COLLATE NOCASE
            """,
            (identifier, identifier),
        ).fetchone()

    if user is None or not password_hasher.verify(
        data.password, user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username/email or password.",
        )

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    access_token = jwt.encode(
        {
            "sub": str(user["id"]),
            "exp": expires_at,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 1800,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
        },
    }


# ---------------- PUBLIC ROUTES ----------------

@app.get("/")
def home():
    return {
        "project": "CloudVault",
        "message": "Welcome to CloudVault!",
        "status": "running",
        "version": "2.0.0",
    }


@app.get("/health")
def health_check():
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")

        return {
            "api": "healthy",
            "database": "connected",
            "storage": get_storage_info(),
        }
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="CloudVault health check failed",
        ) from error


# ---------------- REPLICA HELPERS ----------------

def find_valid_replica(stored_name: str, expected_sha256: str):
    """
    Find a replica whose checksum matches the database metadata.
    The legacy directory is also checked for files uploaded before replication.
    """
    if Path(stored_name).name != stored_name:
        raise HTTPException(status_code=500, detail="Invalid storage metadata.")

    candidates = [
        NODE1_DIR / stored_name,
        NODE2_DIR / stored_name,
        STORAGE_DIR / stored_name,
    ]

    for path in candidates:
        try:
            if path.is_file() and calculate_sha256(path) == expected_sha256:
                return path
        except OSError:
            continue

    raise HTTPException(
        status_code=503,
        detail="No valid file replica is currently available.",
    )


# ---------------- PROTECTED FILE ROUTES ----------------

@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if not file.filename or not file.filename.strip():
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    original_name = Path(file.filename.replace("\\", "/")).name

    if original_name in {"", ".", ".."}:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename.",
        )

    stored_name = uuid.uuid4().hex
    temporary_path = STORAGE_DIR / stored_name
    size = 0
    digest = hashlib.sha256()
    replicas_created = False

    try:
        # Stream the upload to a temporary file while enforcing the size limit.
        with temporary_path.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 20 MB limit.",
                    )

                digest.update(chunk)
                output.write(chunk)

        checksum = digest.hexdigest()

        # Write and verify both replicas before creating database metadata.
        replication = store_replicated_file(
            temporary_path,
            stored_name,
        )
        replicas_created = True

        if replication["sha256"] != checksum:
            raise IOError("Replicated file checksum does not match upload.")

        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO files
                    (filename, stored_name, size_bytes, sha256, user_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    original_name,
                    stored_name,
                    size,
                    checksum,
                    current_user["id"],
                ),
            )
            file_id = cursor.lastrowid
            connection.commit()

        # Remove the temporary source only after both replicas and metadata exist.
        temporary_path.unlink(missing_ok=True)

        return {
            "message": "File uploaded and replicated successfully",
            "id": file_id,
            "filename": original_name,
            "size_bytes": size,
            "sha256": checksum,
            "replication_count": replication["replication_count"],
            "replicas": ["node1", "node2"],
        }

    except HTTPException:
        temporary_path.unlink(missing_ok=True)
        if replicas_created:
            delete_replicas(stored_name)
        raise

    except Exception as error:
        temporary_path.unlink(missing_ok=True)
        if replicas_created:
            try:
                delete_replicas(stored_name)
            except OSError:
                pass

        raise HTTPException(
            status_code=500,
            detail="File upload or replication failed.",
        ) from error

    finally:
        await file.close()


@app.get("/api/files")
def list_files(
    current_user: dict = Depends(get_current_user),
):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, filename, size_bytes, sha256, created_at
            FROM files
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (current_user["id"],),
        ).fetchall()

    return {
        "count": len(rows),
        "files": [dict(row) for row in rows],
    }


@app.get("/api/files/{file_id}/download")
def download_file(
    file_id: int,
    current_user: dict = Depends(get_current_user),
):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT filename, stored_name, sha256
            FROM files
            WHERE id = ? AND user_id = ?
            """,
            (file_id, current_user["id"]),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    path = find_valid_replica(row["stored_name"], row["sha256"])

    return FileResponse(
        path=path,
        filename=row["filename"],
        media_type="application/octet-stream",
    )


@app.delete("/api/files/{file_id}")
def delete_file(
    file_id: int,
    current_user: dict = Depends(get_current_user),
):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT stored_name
            FROM files
            WHERE id = ? AND user_id = ?
            """,
            (file_id, current_user["id"]),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="File not found.",
            )

        stored_name = row["stored_name"]

        connection.execute(
            "DELETE FROM files WHERE id = ? AND user_id = ?",
            (file_id, current_user["id"]),
        )
        connection.commit()

    # Remove all known copies after the metadata deletion succeeds.
    deleted_replicas = delete_replicas(stored_name)
    (STORAGE_DIR / stored_name).unlink(missing_ok=True)

    return {
        "message": "File deleted successfully",
        "id": file_id,
        "replicas_deleted": deleted_replicas,
    }
