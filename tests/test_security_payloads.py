import pytest
import io
from src.app import app, init_app


@pytest.fixture
def client(test_data_dir):
    app.config["TESTING"] = True
    app.config["DATA_DIR"] = str(test_data_dir)
    app.config["BYPASS_AUTH_FOR_TESTING"] = "true"
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.app_context():
        init_app()
    with app.test_client() as client:
        yield client


def test_add_ssh_key_text_valid(client):
    payload = {
        "name": "valid_key",
        "key": "-----BEGIN OPENSSH PRIVATE KEY-----\nvalidkeydata\n",
    }
    response = client.post("/api/keys/text", json=payload)
    assert response.status_code == 200


def test_add_ssh_key_text_invalid_format(client):
    payload = {"name": "invalid_key", "key": "some random text that is not a key"}
    response = client.post("/api/keys/text", json=payload)
    assert response.status_code == 400
    assert b"Invalid SSH key format" in response.data


def test_add_ssh_key_text_too_large(client):
    payload = {
        "name": "large_key",
        "key": "-----BEGIN OPENSSH PRIVATE KEY-----\n" + ("A" * 11000),
    }
    response = client.post("/api/keys/text", json=payload)
    assert response.status_code == 400
    assert b"Payload too large" in response.data


def test_add_ssh_key_text_invalid_json(client):
    response = client.post(
        "/api/keys/text", data="not json", content_type="application/json"
    )
    assert response.status_code == 400


def test_upload_ssh_key_valid(client):
    data = {
        "file": (
            io.BytesIO(b"-----BEGIN OPENSSH PRIVATE KEY-----\nvalidkeydata\n"),
            "valid_file.pem",
        )
    }
    response = client.post(
        "/api/keys/upload", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 200


def test_upload_ssh_key_invalid_format(client):
    data = {"file": (io.BytesIO(b"some random text"), "invalid_file.pem")}
    response = client.post(
        "/api/keys/upload", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 400
    assert b"Invalid SSH key format" in response.data


def test_upload_ssh_key_too_large(client):
    large_content = b"-----BEGIN OPENSSH PRIVATE KEY-----\n" + (b"A" * 11000)
    data = {"file": (io.BytesIO(large_content), "large_file.pem")}
    response = client.post(
        "/api/keys/upload", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 400
    assert b"Payload too large" in response.data


def test_upload_ssh_key_missing_file(client):
    response = client.post(
        "/api/keys/upload", data={}, content_type="multipart/form-data"
    )
    assert response.status_code == 400
    assert b"No file part" in response.data
