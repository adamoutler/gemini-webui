from src.app import validate_ssh_target, fetch_sessions_for_host


def test_validate_ssh_target():
    assert validate_ssh_target("user@host") is True
    assert validate_ssh_target("host.example.com") is True
    assert validate_ssh_target("user@192.168.1.1") is True
    assert validate_ssh_target("user@host; rm -rf /") is False
    assert validate_ssh_target("-oProxyCommand=calc.exe") is False
    assert validate_ssh_target("user@host@other") is False
    assert validate_ssh_target("") is False
    assert validate_ssh_target(None) is False


def test_fetch_sessions_security():
    # Test with malicious host config
    malicious_host = {
        "label": "attack",
        "type": "ssh",
        "target": "user@host; rm -rf /",
        "dir": "/tmp",
    }
    result = fetch_sessions_for_host(malicious_host, "/tmp/.ssh")
    assert "error" in result
    assert "Invalid SSH target" in result["error"]

    malicious_dir = {
        "label": "attack",
        "type": "ssh",
        "target": "user@host",
        "dir": "/tmp; touch /tmp/pwned",
    }
    # This should not execute the touch command because of shlex.quote
    result = fetch_sessions_for_host(malicious_dir, "/tmp/.ssh")
    assert "error" in result
