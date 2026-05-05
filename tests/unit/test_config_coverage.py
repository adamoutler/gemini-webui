from src.config import env_config, AppConfigManager


def test_env_config_properties():
    # Access all properties to ensure they don't raise errors and to provide coverage
    props = [
        "skip_monkey_patch",
        "gemini_bin",
        "admin_user",
        "admin_secret",
        "ldap_server",
        "ldap_base_dn",
        "ldap_bind_user_dn",
        "ldap_bind_secret",
        "ldap_authorized_group",
        "ldap_fallback_domain",
        "allowed_origins_raw",
        "allowed_origins",
        "bypass_auth_for_testing",
        "data_dir",
        "skip_multiplexer",
        "skip_preloader",
        "flask_debug",
        "flask_use_reloader",
        "orphaned_session_ttl",
        "port",
        "ui_port",
        "api_port",
        "secret_key",
    ]
    for prop in props:
        _ = getattr(env_config, prop)


def test_app_config_manager_properties():
    app_config = AppConfigManager()
    app_config._config = {}
    props = [
        "admin_user",
        "admin_secret",
        "ldap_server",
        "ldap_base_dn",
        "ldap_bind_user_dn",
        "ldap_bind_secret",
        "ldap_authorized_group",
        "ldap_fallback_domain",
        "secret_key",
        "data_dir",
        "ssh_dir",
    ]
    for prop in props:
        _ = getattr(app_config, prop)
