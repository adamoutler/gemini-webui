from src.services.process_engine import validate_ssh_target


def test_validate_ssh_target():
    assert validate_ssh_target("user@host:22") is True
    assert validate_ssh_target("host") is True
    assert validate_ssh_target("") is False
    assert validate_ssh_target("invalid target!") is False
