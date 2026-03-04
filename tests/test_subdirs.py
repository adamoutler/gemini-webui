import pytest
import os
import io
import json
from src.app import app, init_app

def test_upload_file_subdirectory(client, test_data_dir):
    data = {
        'file': (io.BytesIO(b"test content"), 'subfolder/testfile.txt')
    }
    response = client.post('/api/upload', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    resp_data = json.loads(response.data)
    assert resp_data['status'] == 'success'
    
    save_path = os.path.join(test_data_dir, 'subfolder/testfile.txt')
    assert os.path.exists(save_path), "File should be saved in subfolder"

def test_download_file_subdirectory(client, test_data_dir):
    save_dir = os.path.join(test_data_dir, 'subfolder')
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, 'download_test.txt')
    with open(save_path, 'wb') as f:
        f.write(b"download content")

    response = client.get('/api/download/subfolder/download_test.txt')
    assert response.status_code == 200
    assert response.data == b"download content"
