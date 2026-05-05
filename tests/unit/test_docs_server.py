from unittest.mock import patch
from src.docs_server import run_docs_server, openapi


def test_openapi():
    # Test openapi route
    with patch("src.docs_server.send_from_directory") as mock_send:
        mock_send.return_value = "file_content"
        result = openapi()
        assert result == "file_content"
        mock_send.assert_called_once()


def test_run_docs_server():
    with patch("src.docs_server.app.run") as mock_run:
        run_docs_server()
        mock_run.assert_called_once_with(host="127.0.0.1", port=8000, debug=False)
