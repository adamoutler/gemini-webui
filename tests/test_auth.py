import pytest
import os

def test_health_no_auth(client):
    """Health check should be accessible without auth."""
    response = client.get('/api/health')
    assert response.status_code == 200

def test_api_requires_auth(client):
    """API endpoints should require authentication when not bypassed."""
    # Ensure bypass is OFF for this test
    os.environ['BYPASS_AUTH_FOR_TESTING'] = 'false'
    client.application.config['BYPASS_AUTH_FOR_TESTING'] = 'false'
    
    # Force logout
    with client.session_transaction() as sess:
        sess['authenticated'] = False
        
    response = client.get('/api/config')
    assert response.status_code == 401
    
    # Restore bypass for other tests
    os.environ['BYPASS_AUTH_FOR_TESTING'] = 'true'
    client.application.config['BYPASS_AUTH_FOR_TESTING'] = 'true'

def test_api_auth_bypass(client):
    """API endpoints should be accessible when bypass is ON."""
    os.environ['BYPASS_AUTH_FOR_TESTING'] = 'true'
    client.application.config['BYPASS_AUTH_FOR_TESTING'] = 'true'
    
    response = client.get('/api/config')
    assert response.status_code == 200

def test_hosts_management(client):
    """Test adding and removing hosts."""
    # Add a test host
    new_host = {"label": "Test Host", "type": "local"}
    response = client.post('/api/hosts', json=new_host)
    assert response.status_code == 200
    
    # Verify it's in the list
    response = client.get('/api/hosts')
    hosts = response.get_json()
    assert any(h['label'] == "Test Host" for h in hosts)
    
    # Delete it
    response = client.delete('/api/hosts/Test%20Host')
    assert response.status_code == 200
    
    # Verify it's gone
    response = client.get('/api/hosts')
    hosts = response.get_json()
    assert not any(h['label'] == "Test Host" for h in hosts)

def test_local_box_protection(client):
    """Local Box should not be deletable."""
    response = client.delete('/api/hosts/Local%20Box')
    assert response.status_code == 403
    
    # Verify it's still there
    response = client.get('/api/hosts')
    hosts = response.get_json()
    assert any(h['label'] == "Local Box" for h in hosts)
