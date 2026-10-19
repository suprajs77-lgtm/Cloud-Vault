
from pathlib import Path
import hashlib
import shutil

BASE_DIR = Path(__file__).resolve().parent.parent

# Two storage nodes on your computer
STORAGE_ROOT = BASE_DIR / "storage"

NODE1_DIR = STORAGE_ROOT / "node1"
NODE2_DIR = STORAGE_ROOT / "node2"

# Keep these paths for compatibility with existing code
STORAGE_DIR = BASE_DIR / "storage" / "files"
VERSIONS_DIR = BASE_DIR / "storage" / "versions"

for directory in (
    NODE1_DIR,
    NODE2_DIR,
    STORAGE_DIR,
    VERSIONS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)


def get_storage_info():
    """Return information about configured storage locations."""
    return {
        "files_directory_exists": STORAGE_DIR.is_dir(),
        "versions_directory_exists": VERSIONS_DIR.is_dir(),
        "node1_exists": NODE1_DIR.is_dir(),
        "node2_exists": NODE2_DIR.is_dir(),
    }


def store_replicated_file(source_path, stored_name):
    """
    Store two copies of a file, one on each storage node.
    Returns information about the copies created.
    """
    source = Path(source_path)

    if not source.is_file():
        raise FileNotFoundError("The source file does not exist.")

    if Path(stored_name).name != stored_name:
        raise ValueError("Invalid stored filename.")

    node1_file = NODE1_DIR / stored_name
    node2_file = NODE2_DIR / stored_name

    try:
        shutil.copy2(source, node1_file)
        shutil.copy2(source, node2_file)

        # Verify that both copies contain identical data.
        source_hash = calculate_sha256(source)

        if (
            calculate_sha256(node1_file) != source_hash
            or calculate_sha256(node2_file) != source_hash
        ):
            raise IOError("Replication verification failed.")

        return {
            "stored_name": stored_name,
            "replicas": [
                str(node1_file.relative_to(BASE_DIR)),
                str(node2_file.relative_to(BASE_DIR)),
            ],
            "sha256": source_hash,
            "replication_count": 2,
        }

    except Exception:
        # Avoid leaving incomplete copies behind.
        node1_file.unlink(missing_ok=True)
        node2_file.unlink(missing_ok=True)
        raise


def calculate_sha256(file_path):
    """Calculate a file's SHA-256 checksum."""
    digest = hashlib.sha256()

    with Path(file_path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def get_available_replica(stored_name):
    """Return an existing copy, preferring Node 1."""
    if Path(stored_name).name != stored_name:
        raise ValueError("Invalid stored filename.")

    for node_dir in (NODE1_DIR, NODE2_DIR):
        replica = node_dir / stored_name

        if replica.is_file():
            return replica

    raise FileNotFoundError("No available replica was found.")


def delete_replicas(stored_name):
    """Delete a file from both storage nodes."""
    if Path(stored_name).name != stored_name:
        raise ValueError("Invalid stored filename.")

    deleted_count = 0

    for node_dir in (NODE1_DIR, NODE2_DIR):
        replica = node_dir / stored_name

        if replica.is_file():
            replica.unlink()
            deleted_count += 1

    return deleted_count
