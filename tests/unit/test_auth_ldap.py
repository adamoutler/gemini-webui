import pytest
from unittest.mock import MagicMock, patch
from src.auth_ldap import sanitize_ldap_input, check_auth


@pytest.mark.timeout(60)
def test_sanitize_ldap_input():
    assert sanitize_ldap_input("user") == "user"
    assert sanitize_ldap_input("user(name)") == r"user\28name\29"
    assert sanitize_ldap_input("user*") == r"user\2a"
    assert sanitize_ldap_input("user\\") == r"user\5c"
    assert sanitize_ldap_input(None) == ""


@patch("ldap3.Server")
@patch("ldap3.Connection")
@pytest.mark.timeout(60)
def test_check_auth_simple_success(mock_connection, mock_server):
    # Setup mock
    mock_conn_instance = MagicMock()
    mock_connection.return_value = mock_conn_instance

    # Run
    result = check_auth(
        "user", "pass", "ldaps://test", "dc=test", ldap_fallback_domain="test.com"
    )

    assert result is True
    mock_connection.assert_called()


@patch("ldap3.Server")
@patch("ldap3.Connection")
@pytest.mark.timeout(60)
def test_check_auth_ad_success(mock_connection, mock_server):
    mock_conn_instance = MagicMock()
    mock_connection.return_value = mock_conn_instance

    # Mock search results for group check
    # Entry behaves like a dict for attributes
    mock_entry = MagicMock()
    mock_entry.entry_dn = "cn=user,dc=test"
    mock_entry.__getitem__.side_effect = (
        lambda x: ["CN=allowed,OU=Groups,dc=test"] if x == "memberOf" else []
    )
    mock_entry.__contains__.side_effect = lambda x: x == "memberOf"

    mock_conn_instance.entries = [mock_entry]

    result = check_auth(
        "user",
        "pass",
        "ldaps://test",
        "dc=test",
        ldap_bind_user_dn="bind_user",
        ldap_bind_pass="bind_pass",
        ldap_authorized_group="allowed",
    )

    assert result is True


@patch("ldap3.Server")
@patch("ldap3.Connection")
@pytest.mark.timeout(60)
def test_check_auth_ad_user_not_found(mock_connection, mock_server):
    mock_conn_instance = MagicMock()
    mock_connection.return_value = mock_conn_instance
    mock_conn_instance.entries = []

    result = check_auth(
        "user",
        "pass",
        "ldaps://test",
        "dc=test",
        ldap_bind_user_dn="bind_user",
        ldap_bind_pass="bind_pass",
    )

    assert result is False


@patch("ldap3.Server")
@patch("ldap3.Connection")
@pytest.mark.timeout(60)
def test_check_auth_ad_group_mismatch(mock_connection, mock_server):
    mock_conn_instance = MagicMock()
    mock_connection.return_value = mock_conn_instance

    mock_entry = MagicMock()
    mock_entry.entry_dn = "cn=user,dc=test"
    mock_entry.__getitem__.side_effect = (
        lambda x: ["CN=wrong,OU=Groups,dc=test"] if x == "memberOf" else []
    )
    mock_entry.__contains__.side_effect = lambda x: x == "memberOf"
    mock_conn_instance.entries = [mock_entry]

    result = check_auth(
        "user",
        "pass",
        "ldaps://test",
        "dc=test",
        ldap_bind_user_dn="bind_user",
        ldap_bind_pass="bind_pass",
        ldap_authorized_group="allowed",
    )

    assert result is False


@patch("ldap3.Server")
@patch("ldap3.Connection")
@pytest.mark.timeout(60)
def test_check_auth_exception(mock_connection, mock_server):
    # Setup mock to fail during the first connection call
    mock_connection.side_effect = Exception("LDAP Down")

    result = check_auth("user", "pass", "ldaps://test", "dc=test")

    assert result is False
