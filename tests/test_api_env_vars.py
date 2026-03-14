import pytest
import json
from src.app import app, init_app


@pytest.fixture
def client(tmp_path):
    app.config["TESTING"] = True
    app.config["DATA_DIR"] = str(tmp_path)
    app.config["BYPASS_AUTH_FOR_TESTING"] = "true"
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.app_context():
        init_app()
    with app.test_client() as client:
        yield client


def test_api_hosts_env_vars_valid(client):
    new_host = {
        "label": "EnvHost1",
        "type": "ssh",
        "target": "user@host",
        "env_vars": {"MY_VAR_1": "value1", "ANOTHER_VAR": "value 2 with spaces!"},
    }
    response = client.post("/api/hosts", json=new_host)
    assert response.status_code == 200

    response = client.get("/api/hosts")
    hosts = json.loads(response.data)
    env_host = next(h for h in hosts if h["label"] == "EnvHost1")
    assert "env_vars" in env_host
    assert env_host["env_vars"]["MY_VAR_1"] == "value1"
    assert env_host["env_vars"]["ANOTHER_VAR"] == "value 2 with spaces!"


def test_api_hosts_env_vars_invalid_type(client):
    new_host = {"label": "EnvHost2", "env_vars": "string_not_dict"}
    response = client.post("/api/hosts", json=new_host)
    assert response.status_code == 400
    assert b"env_vars must be a dictionary" in response.data


def test_api_hosts_env_vars_too_many(client):
    new_host = {
        "label": "EnvHost3",
        "env_vars": {f"VAR_{i}": str(i) for i in range(21)},
    }
    response = client.post("/api/hosts", json=new_host)
    assert response.status_code == 400
    assert b"Too many environment variables" in response.data


def test_api_hosts_env_vars_invalid_key_value_type(client):
    new_host = {"label": "EnvHost4", "env_vars": {"MY_VAR": 123}}
    response = client.post("/api/hosts", json=new_host)
    assert response.status_code == 400
    assert b"env_vars keys and values must be strings" in response.data


def test_api_hosts_env_vars_key_too_long(client):
    new_host = {"label": "EnvHost5", "env_vars": {"A" * 256: "val"}}
    response = client.post("/api/hosts", json=new_host)
    assert response.status_code == 400
    assert b"env_vars keys or values too long" in response.data


def test_api_hosts_env_vars_value_too_long(client):
    new_host = {"label": "EnvHost6", "env_vars": {"VAR": "A" * 1025}}
    response = client.post("/api/hosts", json=new_host)
    assert response.status_code == 400
    assert b"env_vars keys or values too long" in response.data


def test_api_hosts_env_vars_invalid_chars(client):
    invalid_keys = ["MY VAR", "MY-VAR", "MY.VAR", "echo hello;", "$(command)"]
    for key in invalid_keys:
        new_host = {"label": "EnvHost7", "env_vars": {key: "val"}}
        response = client.post("/api/hosts", json=new_host)
        assert response.status_code == 400
        assert b"env_vars keys must be alphanumeric and underscores" in response.data
