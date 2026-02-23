import os
import json
import pytest

def test_get_config(client):
    response = client.get('/api/config')
    assert response.status_code == 200
    data = response.get_json()
    assert 'DEFAULT_SSH_TARGET' in data

def test_update_config(client):
    new_config = {"DEFAULT_SSH_TARGET": "testuser@testhost"}
    response = client.post('/api/config', json=new_config)
    assert response.status_code == 200
    
    # Verify it saved
    response = client.get('/api/config')
    data = response.get_json()
    assert data['DEFAULT_SSH_TARGET'] == "testuser@testhost"

def test_add_ssh_key_text(client):
    key_data = {
        "name": "test_key",
        "key": "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----\n"
    }
    response = client.post('/api/keys/text', json=key_data)
    assert response.status_code == 200
    
    # Verify file exists
    data_dir = client.application.config['DATA_DIR']
    key_path = os.path.join(data_dir, ".ssh", "test_key")
    assert os.path.exists(key_path)
    with open(key_path, 'r') as f:
        content = f.read()
        assert "BEGIN OPENSSH PRIVATE KEY" in content

def test_health_check(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'
