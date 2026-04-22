import pytest
import json
from unittest.mock import MagicMock
from src.app import session_manager


@pytest.mark.timeout(60)
def test_api_search_files_no_session(client):
    response = client.get("/api/sessions/nonexistent_session/search_files?q=app")
    assert response.status_code == 404
    data = json.loads(response.data)
    assert data == {"error": "Session not found"}


@pytest.mark.timeout(60)
def test_api_search_files_success(client):
    # Mock a session
    mock_session = MagicMock()
    mock_session.tab_id = "test_session_123"
    mock_session.user_id = "admin"
    mock_session.file_cache = ["src/app.py", "tests/test_app.py", "README.md"]

    session_manager.sessions["test_session_123"] = mock_session

    # Test successful search
    response = client.get("/api/sessions/test_session_123/search_files?q=app.py")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "matches" in data
    # Exact basename scores highest
    assert data["matches"] == ["src/app.py", "tests/test_app.py"]

    # Clean up
    del session_manager.sessions["test_session_123"]


@pytest.mark.timeout(60)
def test_api_search_files_empty_query(client):
    mock_session = MagicMock()
    mock_session.tab_id = "test_session_123"
    mock_session.user_id = "admin"
    mock_session.file_cache = ["src/app.py", "tests/test_app.py"]

    session_manager.sessions["test_session_123"] = mock_session

    # Empty query should return the whole cache
    response = client.get("/api/sessions/test_session_123/search_files")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "matches" in data
    assert len(data["matches"]) == 2

    # Clean up
    del session_manager.sessions["test_session_123"]
