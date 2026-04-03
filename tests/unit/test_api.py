import pytest
import json
import os
from src.app import app, init_app


@pytest.fixture
def client(test_data_dir):
    app.config["TESTING"] = True
    app.config["DATA_DIR"] = str(test_data_dir)
    app.config["BYPASS_AUTH_FOR_TESTING"] = "true"
    app.config["SECRET_KEY"] = "test-secret-key"
    # Force initialization to set up globals and paths
    with app.app_context():
        init_app()
    with app.test_client() as client:
        yield client


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data == {"status": "ok"}


def test_api_hosts_lifecycle(client):
    # 1. List initial hosts (may have more than 1 if other tests added hosts)
    response = client.get("/api/hosts")
    assert response.status_code == 200
    hosts = json.loads(response.data)
    initial_count = len(hosts)
    assert initial_count >= 1
    assert any(h["label"] == "local" for h in hosts)

    # 2. Add a new host
    new_host = {
        "label": "TestHost",
        "type": "ssh",
        "target": "user@host",
        "dir": "/tmp",
    }
    response = client.post(
        "/api/hosts", data=json.dumps(new_host), content_type="application/json"
    )
    assert response.status_code == 200
    assert json.loads(response.data) == {"status": "success"}

    # 3. Verify it was added
    response = client.get("/api/hosts")
    assert response.status_code == 200
    hosts = json.loads(response.data)
    assert isinstance(hosts, list)
    assert any(h["label"] == "TestHost" for h in hosts)

    # 4. Edit the host (in-place)
    edited_host = new_host.copy()
    edited_host["dir"] = "/home/user"
    edited_host["old_label"] = "TestHost"
    response = client.post(
        "/api/hosts", data=json.dumps(edited_host), content_type="application/json"
    )
    assert response.status_code == 200
    assert json.loads(response.data) == {"status": "success"}

    # 5. Reorder hosts
    reorder_data = ["TestHost", "local"]
    response = client.post(
        "/api/hosts/reorder",
        data=json.dumps(reorder_data),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert json.loads(response.data) == {"status": "success"}

    response = client.get("/api/hosts")
    assert response.status_code == 200
    hosts = json.loads(response.data)
    assert hosts[0]["label"] == "TestHost"

    # 6. Remove the host
    response = client.delete("/api/hosts/TestHost")
    assert response.status_code == 200
    assert json.loads(response.data) == {"status": "success"}
    response = client.get("/api/hosts")
    assert response.status_code == 200
    hosts = json.loads(response.data)
    assert not any(h["label"] == "TestHost" for h in hosts)


def test_api_config(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    conf = json.loads(response.data)
    assert isinstance(conf, dict)
    assert "HOSTS" in conf
    assert isinstance(conf["HOSTS"], list)
    assert "LDAP_BIND_PASS" not in conf
    assert "ADMIN_PASS" not in conf


def test_api_keys_list(client, test_data_dir):
    # Setup some keys in the ssh directory
    ssh_dir = os.path.join(str(test_data_dir), ".ssh")
    os.makedirs(ssh_dir, exist_ok=True)

    # Clear existing files for a deterministic test
    for f in os.listdir(ssh_dir):
        os.remove(os.path.join(ssh_dir, f))

    with open(os.path.join(ssh_dir, "test_key"), "w") as f:
        f.write("private_key_content")
    with open(os.path.join(ssh_dir, "test_key.pub"), "w") as f:
        f.write("public_key_content")

    response = client.get("/api/keys")
    assert response.status_code == 200
    keys = json.loads(response.data)
    assert isinstance(keys, list)
    # Check that keys contain only strings and verify they are expected files
    assert all(isinstance(k, str) for k in keys)
    assert set(keys) == {"test_key", "test_key.pub"}


def test_api_keys_public(client, test_data_dir):
    ssh_dir = os.path.join(str(test_data_dir), ".ssh")
    os.makedirs(ssh_dir, exist_ok=True)

    # clear existing files to test 404
    for f in os.listdir(ssh_dir):
        os.remove(os.path.join(ssh_dir, f))

    # Test 404 behavior when key doesn't exist
    response = client.get("/api/keys/public")
    assert response.status_code == 404
    assert json.loads(response.data) == {"error": "Public key not found"}

    # Test 200 behavior when key exists
    pub_key_path = os.path.join(ssh_dir, "id_ed25519.pub")
    with open(pub_key_path, "w") as f:
        f.write("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test@example.com")

    response = client.get("/api/keys/public")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data == {"key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test@example.com"}


def test_api_export_settings(client, test_data_dir):
    # Ensure there's something to zip
    test_file_path = os.path.join(test_data_dir, "test_file.txt")
    with open(test_file_path, "w") as f:
        f.write("test content")

    response = client.get("/api/settings/export")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/zip"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "settings.gwui" in response.headers["Content-Disposition"]
    assert len(response.data) > 0


def test_api_import_settings(client, test_data_dir):
    import zipfile
    import io

    # Create a dummy zip file in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w") as zf:
        zf.writestr("imported_file.txt", "imported content")
    memory_file.seek(0)

    # Send it to the import endpoint
    data = {"file": (memory_file, "backup.gwui")}
    response = client.post(
        "/api/settings/import", data=data, content_type="multipart/form-data"
    )

    assert response.status_code == 200
    assert response.json["success"] is True

    # Verify the file was extracted into the data dir
    extracted_file = os.path.join(test_data_dir, "imported_file.txt")
    assert os.path.exists(extracted_file)
    with open(extracted_file, "r") as f:
        assert f.read() == "imported content"
