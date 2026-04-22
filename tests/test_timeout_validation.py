import pytest
import time
import requests


@pytest.mark.timeout(5)
def test_fast_timeout_success():
    """This test should pass quickly."""
    assert True


@pytest.mark.timeout(10)
def test_network_timeout_standard(server):
    """Standard test involving a network request with a timeout."""
    response = requests.get(server + "/health", timeout=5)
    assert response.status_code == 200


@pytest.mark.timeout(60)
def test_global_timeout_fallback():
    """
    This test relies on the global --timeout=60 fallback defined in pytest.ini.
    It's better to use @pytest.mark.timeout for granular control.
    """
    assert True
