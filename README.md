# CloudVault — Cloud Distribution System

A secure file-storage backend built with FastAPI, SQLite, and Python-based replicated storage. CloudVault supports user authentication, file uploads and downloads, metadata management, and replication across two storage nodes.

## Features

- **User Authentication:** User registration and login with JWT-based authentication.
- **Secure File Access:** Users can access their own files through protected API endpoints.
- **File Upload and Download:** Upload, retrieve, and manage files through a web dashboard.
- **Replicated Storage:** Store two copies of uploaded files across Node 1 and Node 2.
- **Data Integrity:** Verify file contents using SHA-256 checksums.
- **Replica Recovery:** Retrieve an available copy when the preferred replica is missing.
- **File Management:** Delete file records and their associated replicas.
- **Metadata Management:** Store file information in SQLite.
- **Automated Testing:** Test API health, authentication, file operations, and replication.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Database | SQLite |
| Authentication | JWT |
| File Integrity | SHA-256 |
| Frontend | HTML, CSS, JavaScript |
| API Testing | Pytest, FastAPI TestClient |
| Development | VS Code, PowerShell |

## Architecture

```text
             Web Dashboard
                   |
                   v
             FastAPI Backend
                   |
          +--------+--------+
          |        |        |
          v        v        v
     Authentication SQLite  File Service
          |        |        |
          |        |        v
          |        |   SHA-256 Verification
          |        |        |
          |        |   +----+----+
          |        |   |         |
          |        |   v         v
          |        | Node 1    Node 2
          |        |   |         |
          |        |   +----+----+
          |        |      Replicas
          +--------+----------------
```

**Note:** Node 1 and Node 2 are separate storage directories on the same development machine. The project demonstrates replication and replica fallback, but does not yet provide physical multi-server distribution.

## Project Structure

```text
CloudVault/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   └── storage_service.py
├── frontend/
│   ├── index.html
│   └── login.html
├── storage/
│   ├── files/
│   ├── versions/
│   ├── node1/
│   └── node2/
├── tests/
│   ├── test_api.py
│   ├── test_auth.py
│   └── test_files.py
├── requirements.txt
└── README.md
```

## Installation and Setup

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd CloudVault
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest httpx
```

### 4. Configure the JWT secret

```powershell
$env:CLOUDVAULT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

For local development, this generates a secret for the current terminal session. Configure a persistent secret securely for deployment.

### 5. Start the backend

```powershell
python -m uvicorn app.main:app --reload
```

API base URL: `http://127.0.0.1:8000`

Interactive API documentation: `http://127.0.0.1:8000/docs`

### 6. Start the frontend

Open a second PowerShell terminal:

```powershell
python -m http.server 5500 --directory frontend --bind 127.0.0.1
```

Open `http://127.0.0.1:5500/login.html` in your browser.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | API status |
| GET | `/health` | API, database, and storage health |
| POST | `/api/auth/signup` | Register a user |
| POST | `/api/auth/login` | Authenticate a user |
| POST | `/api/files/upload` | Upload a file |
| GET | `/api/files` | List the authenticated user's files |
| GET | `/api/files/{file_id}/download` | Download a file |
| DELETE | `/api/files/{file_id}` | Delete a file and its replicas |

Confirm the endpoint names against the current API documentation if they differ.

## Run Automated Tests

Run the complete test suite:

```powershell
python -m pytest tests -v
```

The tests cover API health, user authentication, protected access, file upload, replication integrity, download, and deletion.

Record the actual test results in this README after running the suite.

## Future Improvements

- Deploy storage nodes on separate machines or cloud instances.
- Add cloud object storage integration.
- Implement automatic replica repair and background health monitoring.
- Add file versioning and configurable retention policies.
- Improve automated testing and continuous integration.
- Add rate limiting, audit logging, and production security controls.

## Learning Outcomes

This project demonstrates backend API development, authentication, database integration, file handling, integrity verification, replication concepts, fault recovery, and automated testing.
