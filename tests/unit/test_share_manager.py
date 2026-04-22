import pytest
import time
import concurrent.futures
from pathlib import Path

from src.share_manager import ShareManager


@pytest.fixture
def temp_share_manager(tmp_path):
    manager = ShareManager(data_dir=str(tmp_path))
    return manager


@pytest.mark.timeout(60)
def test_create_and_get_share(temp_share_manager):
    html = "<html><body><h1>Session Snapshot</h1></body></html>"
    name = "My Session"

    share_id = temp_share_manager.create_share(html, name)
    assert share_id is not None

    metadata = temp_share_manager.get_share_metadata(share_id)
    assert metadata is not None
    assert metadata["id"] == share_id
    assert metadata["session_name"] == name
    assert "created_at" in metadata
    assert "file_path" in metadata

    file_path = Path(metadata["file_path"])
    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == html


@pytest.mark.timeout(60)
def test_get_nonexistent_share(temp_share_manager):
    metadata = temp_share_manager.get_share_metadata("nonexistent-id")
    assert metadata is None


@pytest.mark.timeout(60)
def test_list_shares(temp_share_manager):
    shares = temp_share_manager.list_shares()
    assert len(shares) == 0

    id1 = temp_share_manager.create_share("html1", "session1")
    time.sleep(0.01)  # ensure different timestamps for ordering
    id2 = temp_share_manager.create_share("html2", "session2")

    shares = temp_share_manager.list_shares()
    assert len(shares) == 2
    # Should be ordered by created_at DESC (newest first)
    assert shares[0]["id"] == id2
    assert shares[1]["id"] == id1


@pytest.mark.timeout(60)
def test_delete_share(temp_share_manager):
    share_id = temp_share_manager.create_share("html", "session")

    metadata = temp_share_manager.get_share_metadata(share_id)
    file_path = Path(metadata["file_path"])
    assert file_path.exists()

    success = temp_share_manager.delete_share(share_id)
    assert success is True

    # Verify file is deleted
    assert not file_path.exists()

    # Verify metadata is deleted
    metadata_after = temp_share_manager.get_share_metadata(share_id)
    assert metadata_after is None

    # Delete again should return False
    success_again = temp_share_manager.delete_share(share_id)
    assert success_again is False


@pytest.mark.timeout(60)
def test_concurrent_creation(temp_share_manager):
    def create_share_worker(i):
        return temp_share_manager.create_share(f"html{i}", f"session{i}")

    num_threads = 20
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(create_share_worker, i) for i in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == num_threads

    shares = temp_share_manager.list_shares()
    assert len(shares) == num_threads
