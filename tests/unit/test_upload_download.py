import pytest
import os
import io
import json
from src.app import app, init_app


@pytest.fixture
def client(test_data_dir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(test_data_dir))
    app.config["TESTING"] = True
    app.config["DATA_DIR"] = str(test_data_dir)
    app.config["BYPASS_AUTH_FOR_TESTING"] = "true"
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.app_context():
        init_app()
    with app.test_client() as client:
        yield client


def test_upload_file_success(client, test_data_dir):
    data = {"file": (io.BytesIO(b"test content"), "testfile.txt")}
    response = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    resp_data = json.loads(response.data)
    assert resp_data["status"] == "success"
    assert resp_data["filename"] == "testfile.txt"

    # Verify file is saved in DATA_DIR/workspace
    save_path = os.path.join(test_data_dir, "workspace", "testfile.txt")
    assert os.path.exists(save_path)
    with open(save_path, "rb") as f:
        assert f.read() == b"test content"


def test_upload_file_no_file(client):
    response = client.post("/api/upload", data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    resp_data = json.loads(response.data)
    assert resp_data["message"] == "No file part"


from unittest.mock import patch, MagicMock


def test_upload_file_ssh_proxy(client, test_data_dir):
    data = {
        "file": (io.BytesIO(b"test content"), "testfile.txt"),
        "ssh_target": "user@host",
        "ssh_dir": "/remote/dir",
    }
    with patch("src.routes.api.subprocess.run") as mock_run, patch(
        "src.app.validate_ssh_target", return_value=True
    ), patch(
        "src.config.get_config_paths",
        return_value=("/tmp", "/tmp/config", "/tmp/ssh_dir"),
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="mock_path")
        response = client.post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert response.status_code == 200
        resp_data = json.loads(response.data)
        assert resp_data["status"] == "success"
        assert resp_data["filename"] == "mock_path"

        assert mock_run.call_count == 4
        ssh_call = mock_run.call_args_list[0][0][0]
        scp_call = mock_run.call_args_list[1][0][0]
        verify_call = mock_run.call_args_list[2][0][0]
        path_call = mock_run.call_args_list[3][0][0]

        import os
        import shlex
        from src.process_manager import build_ssh_args

        base_ssh_args = build_ssh_args("user@host", "/tmp/ssh_dir")[1:]
        workspace_dir = os.path.join(test_data_dir, "workspace")
        save_path = os.path.abspath(os.path.join(workspace_dir, "testfile.txt"))

        expected_ssh_call = (
            ["ssh"]
            + base_ssh_args
            + ["--", "user@host", f"mkdir -p {shlex.quote('/remote/dir')}"]
        )
        expected_scp_call = (
            ["scp"]
            + base_ssh_args
            + ["--", save_path, "user@host:/remote/dir/testfile.txt"]
        )
        expected_verify_call = (
            ["ssh"]
            + base_ssh_args
            + ["--", "user@host", f"ls {shlex.quote('/remote/dir/testfile.txt')}"]
        )
        expected_path_call = (
            ["ssh"]
            + base_ssh_args
            + [
                "--",
                "user@host",
                f"realpath {shlex.quote('/remote/dir/testfile.txt')} 2>/dev/null || readlink -m {shlex.quote('/remote/dir/testfile.txt')} 2>/dev/null || echo {shlex.quote('/remote/dir/testfile.txt')}",
            ]
        )

        assert "ssh" in ssh_call
        assert any("user@host" in arg for arg in ssh_call)
        assert "scp" in scp_call
        assert any("user@host" in arg for arg in scp_call)
        assert "ssh" in verify_call
        assert any("ls" in arg for arg in verify_call)
        assert "ssh" in path_call
        assert any("realpath" in arg for arg in path_call)


def test_upload_file_ssh_proxy_home_dir(client, test_data_dir):
    data = {
        "file": (io.BytesIO(b"test content"), "testfile.txt"),
        "ssh_target": "user@host",
        "ssh_dir": "~",
    }
    with patch("src.routes.api.subprocess.run") as mock_run, patch(
        "src.app.validate_ssh_target", return_value=True
    ), patch(
        "src.config.get_config_paths",
        return_value=("/tmp", "/tmp/config", "/tmp/ssh_dir"),
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="mock_path")
        response = client.post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert response.status_code == 200

        # In this case, remote_dir is empty string, so ssh mkdir is not called
        assert mock_run.call_count == 3
        scp_call = mock_run.call_args_list[0][0][0]
        verify_call = mock_run.call_args_list[1][0][0]
        path_call = mock_run.call_args_list[2][0][0]

        import os
        import shlex
        from src.process_manager import build_ssh_args

        base_ssh_args = build_ssh_args("user@host", "/tmp/ssh_dir")[1:]
        workspace_dir = os.path.join(test_data_dir, "workspace")
        save_path = os.path.abspath(os.path.join(workspace_dir, "testfile.txt"))

        expected_scp_call = (
            ["scp"] + base_ssh_args + ["--", save_path, "user@host:testfile.txt"]
        )
        expected_verify_call = (
            ["ssh"]
            + base_ssh_args
            + ["--", "user@host", f"ls {shlex.quote('testfile.txt')}"]
        )
        expected_path_call = (
            ["ssh"]
            + base_ssh_args
            + [
                "--",
                "user@host",
                f"realpath {shlex.quote('testfile.txt')} 2>/dev/null || readlink -m {shlex.quote('testfile.txt')} 2>/dev/null || echo {shlex.quote('testfile.txt')}",
            ]
        )

        assert "scp" in scp_call
        assert any("user@host" in arg for arg in scp_call)
        assert "ssh" in verify_call
        assert any("ls" in arg for arg in verify_call)
        assert "ssh" in path_call
        assert any("realpath" in arg for arg in path_call)


def test_download_file_success(client, test_data_dir):
    # Setup file in workspace
    workspace_dir = os.path.join(test_data_dir, "workspace")
    os.makedirs(workspace_dir, exist_ok=True)
    save_path = os.path.join(workspace_dir, "download_test.txt")
    with open(save_path, "wb") as f:
        f.write(b"download content")

    response = client.get("/api/download/download_test.txt")
    assert response.status_code == 200
    assert response.data == b"download content"
    assert response.headers["Content-Disposition"].startswith("attachment;")


def test_upload_file_ssh_proxy_mkdir_failure(client, test_data_dir):
    data = {
        "file": (io.BytesIO(b"test content"), "testfile.txt"),
        "ssh_target": "user@host",
        "ssh_dir": "/remote/dir",
    }
    with patch("src.routes.api.subprocess.run") as mock_run, patch(
        "src.app.validate_ssh_target", return_value=True
    ), patch(
        "src.config.get_config_paths",
        return_value=("/tmp", "/tmp/config", "/tmp/ssh_dir"),
    ):
        mock_run.return_value = MagicMock(returncode=1, stderr="Permission denied")
        response = client.post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data["status"] == "error"
        assert "Failed to create remote directory" in resp_data["message"]


def test_upload_file_ssh_proxy_scp_failure(client, test_data_dir):
    data = {
        "file": (io.BytesIO(b"test content"), "testfile.txt"),
        "ssh_target": "user@host",
        "ssh_dir": "/remote/dir",
    }
    with patch("src.routes.api.subprocess.run") as mock_run, patch(
        "src.app.validate_ssh_target", return_value=True
    ), patch(
        "src.config.get_config_paths",
        return_value=("/tmp", "/tmp/config", "/tmp/ssh_dir"),
    ):

        def run_side_effect(*args, **kwargs):
            if args[0][0] == "scp":
                return MagicMock(returncode=1, stderr="SCP Error")
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect

        response = client.post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data["status"] == "error"
        assert "SCP failed" in resp_data["message"]


def test_upload_file_ssh_proxy_verify_failure(client, test_data_dir):
    data = {
        "file": (io.BytesIO(b"test content"), "testfile.txt"),
        "ssh_target": "user@host",
        "ssh_dir": "/remote/dir",
    }
    with patch("src.routes.api.subprocess.run") as mock_run, patch(
        "src.app.validate_ssh_target", return_value=True
    ), patch(
        "src.config.get_config_paths",
        return_value=("/tmp", "/tmp/config", "/tmp/ssh_dir"),
    ):

        def run_side_effect(*args, **kwargs):
            if args[0][0] == "ssh" and any("ls" in arg for arg in args[0]):
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect

        response = client.post(
            "/api/upload", data=data, content_type="multipart/form-data"
        )

        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data["status"] == "error"
        assert "SCP returned 0, but file verification failed" in resp_data["message"]
