import os


def test_sw_bypass_logic():
    """
    Unit test to verify that the Service Worker bypasses the cache entirely
    for /api/, /socket.io/, and /auth/ routes.
    """
    sw_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "src", "static", "sw.js"
    )
    with open(sw_path, "r") as f:
        content = f.read()

    assert 'url.pathname.startsWith("/api/")' in content
    assert 'url.pathname.startsWith("/socket.io/")' in content
    assert 'url.pathname.startsWith("/auth/")' in content
