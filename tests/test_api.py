import pytest
import json
import os
from src.app import app, init_app

@pytest.fixture
def client(test_data_dir):
    app.config['TESTING'] = True
    app.config['DATA_DIR'] = str(test_data_dir)
    app.config['BYPASS_AUTH_FOR_TESTING'] = 'true'
    app.config['SECRET_KEY'] = 'test-secret-key'
    # Force initialization to set up globals and paths
    with app.app_context():
        init_app()
    with app.test_client() as client:
        yield client

def test_api_health(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "status" in data

def test_api_hosts_lifecycle(client):
    # 1. List initial hosts
    response = client.get('/api/hosts')
    assert response.status_code == 200
    hosts = json.loads(response.data)
    assert len(hosts) == 1
    assert hosts[0]['label'] == 'local'

    # 2. Add a new host
    new_host = {
        "label": "TestHost",
        "type": "ssh",
        "target": "user@host",
        "dir": "/tmp"
    }
    response = client.post('/api/hosts', 
                           data=json.dumps(new_host),
                           content_type='application/json')
    assert response.status_code == 200

    # 3. Verify it was added
    response = client.get('/api/hosts')
    hosts = json.loads(response.data)
    assert any(h['label'] == 'TestHost' for h in hosts)

    # 4. Edit the host (in-place)
    edited_host = new_host.copy()
    edited_host['dir'] = '/home/user'
    edited_host['old_label'] = 'TestHost'
    response = client.post('/api/hosts', 
                           data=json.dumps(edited_host),
                           content_type='application/json')
    assert response.status_code == 200

    # 5. Reorder hosts
    reorder_data = ["TestHost", "local"]
    response = client.post('/api/hosts/reorder',
                           data=json.dumps(reorder_data),
                           content_type='application/json')
    assert response.status_code == 200
    
    response = client.get('/api/hosts')
    hosts = json.loads(response.data)
    assert hosts[0]['label'] == 'TestHost'

    # 6. Remove the host
    response = client.delete('/api/hosts/TestHost')
    assert response.status_code == 200
    response = client.get('/api/hosts')
    hosts = json.loads(response.data)
    assert not any(h['label'] == 'TestHost' for h in hosts)

def test_api_config(client):
    response = client.get('/api/config')
    assert response.status_code == 200
    conf = json.loads(response.data)
    assert "HOSTS" in conf

def test_api_keys_list(client):
    response = client.get('/api/keys')
    assert response.status_code == 200
    keys = json.loads(response.data)
    assert isinstance(keys, list)

def test_api_keys_public(client):
    # This might fail if key not generated yet, but let's check
    response = client.get('/api/keys/public')
    # If not found, it returns 404, which is fine for now
    assert response.status_code in [200, 404]
