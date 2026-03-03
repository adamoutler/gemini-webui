import pytest
from unittest.mock import patch, MagicMock
import os
from src.app import app, init_app

@pytest.fixture
def client(test_data_dir):
    app.config['TESTING'] = True
    app.config['DATA_DIR'] = str(test_data_dir)
    app.config['SECRET_KEY'] = 'test-secret'
    app.config['BYPASS_AUTH_FOR_TESTING'] = 'false'
    # Clear bypass for some tests
    with patch.dict('os.environ', {"BYPASS_AUTH_FOR_TESTING": "false"}):
        with app.app_context():
            init_app()
        with app.test_client() as client:
            yield client

def test_index_route_no_auth(client):
    with patch.dict('os.environ', {"BYPASS_AUTH_FOR_TESTING": "false"}):
        response = client.get('/')
        assert response.status_code == 401

def test_index_route_with_auth(client):
    # Mocking admin user
    with patch('src.app.ADMIN_USER', 'admin'), \
         patch('src.app.ADMIN_PASS', 'admin'), \
         patch('src.app.LDAP_SERVER', None):
        import base64
        headers = {
            'Authorization': 'Basic ' + base64.b64encode(b'admin:admin').decode('utf-8')
        }
        response = client.get('/', headers=headers)
        assert response.status_code == 200

def test_instance_key_generation_logic(client, test_data_dir):
    # Force a run where keys are missing
    ssh_dir = os.path.join(str(test_data_dir), ".ssh")
    if os.path.exists(ssh_dir):
        import shutil
        shutil.rmtree(ssh_dir)
    
    with patch('src.app.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from src.app import init_app
        init_app()
        # Key generation should have been triggered
        assert mock_run.called

def test_health_check_unauthenticated(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    
def test_root_health_check_unauthenticated(client):
    response = client.get('/health')
    assert response.status_code == 200

def test_favicon_routes(client):
    for path in ['/favicon.ico', '/favicon.svg']:
        response = client.get(path)
        assert response.status_code == 200
        assert b'<svg' in response.data
