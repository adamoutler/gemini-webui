import sys

with open("src/app.py", "r") as f:
    content = f.read()

# Replace config = get_config() blocks with app_config
old_config = """    config = get_config()
    ADMIN_USER = config.get("ADMIN_USER", ADMIN_USER)
    ADMIN_PASS = config.get("ADMIN_PASS", ADMIN_PASS)
    LDAP_SERVER = config.get("LDAP_SERVER")
    LDAP_BASE_DN = config.get("LDAP_BASE_DN")
    LDAP_BIND_USER_DN = config.get("LDAP_BIND_USER_DN")
    LDAP_BIND_PASS = config.get("LDAP_BIND_PASS")
    LDAP_AUTHORIZED_GROUP = config.get("LDAP_AUTHORIZED_GROUP")
    LDAP_FALLBACK_DOMAIN = config.get("LDAP_FALLBACK_DOMAIN")

    # Load secret key from config (env) or generate one
    import secrets

    secret_key = config.get("SECRET_KEY") or env_config.SECRET_KEY
    if not secret_key:
        secret_key = secrets.token_hex(32)
        # Persist the generated fallback key if writable
        if config.get("DATA_WRITABLE"):
            try:
                config["SECRET_KEY"] = secret_key
                with open(config_file, "w") as f:
                    json.dump(config, f, indent=4)
                logger.info("Generated and persisted new fallback SECRET_KEY")
            except Exception as e:
                logger.error(f"Failed to persist fallback SECRET_KEY: {e}")
        else:
            logger.warning(
                "SECRET_KEY not found and storage not writable. Sessions will invalidate on restart."
            )"""

new_config = """    app_config.init_config(data_dir)
    secret_key = app_config.SECRET_KEY"""

content = content.replace(old_config, new_config)

# Update return config
content = content.replace(
    "return config", "register_socketio_handlers(app)\n    return app_config"
)

# Update get_config calls
content = content.replace("get_config().get", "app_config.get")

with open("src/app.py", "w") as f:
    f.write(content)
