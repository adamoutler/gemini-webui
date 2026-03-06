import pytest
import os
import io
import json
from src.app import app, init_app

@pytest.fixture
def client(test_data_dir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(test_data_dir))
    app.config['TESTING'] = True
    app.config['DATA_DIR'] = str(test_data_dir)
    app.config['BYPASS_AUTH_FOR_TESTING'] = 'true'
    app.config['SECRET_KEY'] = 'test-secret-key'
    with app.app_context():
        init_app()
    with app.test_client() as client:
        yield client

def test_upload_file_success(client, test_data_dir):
    data = {
        'file': (io.BytesIO(b"test content"), 'testfile.txt')
    }
    response = client.post('/api/upload', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    resp_data = json.loads(response.data)
    assert resp_data['status'] == 'success'
    assert resp_data['filename'] == 'testfile.txt'

    # Verify file is saved in DATA_DIR/workspace
    save_path = os.path.join(test_data_dir, 'workspace', 'testfile.txt')
    assert os.path.exists(save_path)
    with open(save_path, 'rb') as f:
        assert f.read() == b"test content"

def test_upload_file_no_file(client):
    response = client.post('/api/upload', data={}, content_type='multipart/form-data')
    assert response.status_code == 400
    resp_data = json.loads(response.data)
    assert resp_data['message'] == 'No file part'

from unittest.mock import patch, MagicMock

def test_upload_file_ssh_proxy(client, test_data_dir):
    data = {
        'file': (io.BytesIO(b"test content"), 'testfile.txt'),
        'ssh_target': 'user@host',
        'ssh_dir': '/remote/dir'
    }
    with patch('src.app.subprocess.run') as mock_run, \
         patch('src.app.validate_ssh_target', return_value=True), \
         patch('src.app.get_config_paths', return_value=('/tmp', '/tmp/config', '/tmp/ssh_dir')):
        
        mock_run.return_value = MagicMock(returncode=0)
        response = client.post('/api/upload', data=data, content_type='multipart/form-data')
        
        assert response.status_code == 200
        resp_data = json.loads(response.data)
        assert resp_data['status'] == 'success'
        assert resp_data['filename'] == 'testfile.txt'

        assert mock_run.call_count == 3
        ssh_call = mock_run.call_args_list[0][0][0]
        scp_call = mock_run.call_args_list[1][0][0]
        verify_call = mock_run.call_args_list[2][0][0]
        
        assert ssh_call[0] == 'ssh'
        assert 'user@host' in ssh_call
        assert any('mkdir -p' in arg for arg in ssh_call)
        
        assert scp_call[0] == 'scp'
        assert 'user@host:/remote/dir/testfile.txt' in scp_call

        assert verify_call[0] == 'ssh'
        assert 'user@host' in verify_call
        assert any('ls' in arg for arg in verify_call)

def test_upload_file_ssh_proxy_home_dir(client, test_data_dir):
    data = {
        'file': (io.BytesIO(b"test content"), 'testfile.txt'),
        'ssh_target': 'user@host',
        'ssh_dir': '~'
    }
    with patch('src.app.subprocess.run') as mock_run, \
         patch('src.app.validate_ssh_target', return_value=True), \
         patch('src.app.get_config_paths', return_value=('/tmp', '/tmp/config', '/tmp/ssh_dir')):
        
        mock_run.return_value = MagicMock(returncode=0)
        response = client.post('/api/upload', data=data, content_type='multipart/form-data')
        
        assert response.status_code == 200
        
        # In this case, remote_dir is empty string, so ssh mkdir is not called
        assert mock_run.call_count == 2
        scp_call = mock_run.call_args_list[0][0][0]
        verify_call = mock_run.call_args_list[1][0][0]
        
        assert scp_call[0] == 'scp'
        assert 'user@host:testfile.txt' in scp_call

        assert verify_call[0] == 'ssh'
        assert 'user@host' in verify_call
        assert any('ls' in arg for arg in verify_call)

def test_download_file_success(client, test_data_dir):
    # Setup file in workspace
    workspace_dir = os.path.join(test_data_dir, 'workspace')
    os.makedirs(workspace_dir, exist_ok=True)
    save_path = os.path.join(workspace_dir, 'download_test.txt')
    with open(save_path, 'wb') as f:
        f.write(b"download content")

    response = client.get('/api/download/download_test.txt')
    assert response.status_code == 200
    assert response.data == b"download content"
    assert response.headers['Content-Disposition'].startswith('attachment;')

def test_upload_file_ssh_proxy_mkdir_failure(client, test_data_dir):
    data = {
        'file': (io.BytesIO(b"test content"), 'testfile.txt'),
        'ssh_target': 'user@host',
        'ssh_dir': '/remote/dir'
    }
    with patch('src.app.subprocess.run') as mock_run, \
         patch('src.app.validate_ssh_target', return_value=True), \
         patch('src.app.get_config_paths', return_value=('/tmp', '/tmp/config', '/tmp/ssh_dir')):
        
        mock_run.return_value = MagicMock(returncode=1, stderr="Permission denied")
        response = client.post('/api/upload', data=data, content_type='multipart/form-data')
        
        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data['status'] == 'error'
        assert 'Failed to create remote directory' in resp_data['message']

def test_upload_file_ssh_proxy_scp_failure(client, test_data_dir):
    data = {
        'file': (io.BytesIO(b"test content"), 'testfile.txt'),
        'ssh_target': 'user@host',
        'ssh_dir': '/remote/dir'
    }
    with patch('src.app.subprocess.run') as mock_run, \
         patch('src.app.validate_ssh_target', return_value=True), \
         patch('src.app.get_config_paths', return_value=('/tmp', '/tmp/config', '/tmp/ssh_dir')):
        
        def run_side_effect(*args, **kwargs):
            if args[0][0] == 'scp':
                return MagicMock(returncode=1, stderr="SCP Error")
            return MagicMock(returncode=0)
        mock_run.side_effect = run_side_effect
        
        response = client.post('/api/upload', data=data, content_type='multipart/form-data')
        
        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data['status'] == 'error'
        assert 'SCP failed' in resp_data['message']

def test_upload_file_ssh_proxy_verify_failure(client, test_data_dir):
    data = {
        'file': (io.BytesIO(b"test content"), 'testfile.txt'),
        'ssh_target': 'user@host',
        'ssh_dir': '/remote/dir'
    }
    with patch('src.app.subprocess.run') as mock_run, \
         patch('src.app.validate_ssh_target', return_value=True), \
         patch('src.app.get_config_paths', return_value=('/tmp', '/tmp/config', '/tmp/ssh_dir')):
        
        def run_side_effect(*args, **kwargs):
            if args[0][0] == 'ssh' and any('ls' in arg for arg in args[0]):
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)
        mock_run.side_effect = run_side_effect
        
        response = client.post('/api/upload', data=data, content_type='multipart/form-data')
        
        assert response.status_code == 500
        resp_data = json.loads(response.data)
        assert resp_data['status'] == 'error'
        assert 'SCP returned 0, but file verification failed' in resp_data['message']
