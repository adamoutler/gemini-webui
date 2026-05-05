import pytest
from src.services.remote_fs import upload_to_remote


def test_upload_to_remote_invalid_target():
    with pytest.raises(ValueError, match="Invalid SSH target"):
        upload_to_remote("/tmp/test", "test.txt", "invalid target!", "", "")
