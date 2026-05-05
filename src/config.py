import os
import json
import logging
import socket
import hashlib


class EnvConfig:
    @property
    def skip_monkey_patch(self):
        return os.environ.get("SKIP_MONKEY_PATCH") == "true"

    @property
    def gemini_bin(self):
        return os.environ.get("GEMINI_BIN", "gemini")

    @property
    def admin_user(self):
        return os.environ.get("ADMIN_USER", "admin")

    @property
    def admin_secret(self):
        return os.environ.get("ADMIN_PASS", "admin")

    @property
    def ldap_server(self):
        return os.environ.get("LDAP_SERVER")

    @property
    def ldap_base_dn(self):
        return os.environ.get("LDAP_BASE_DN")

    @property
    def ldap_bind_user_dn(self):
        return os.environ.get("LDAP_BIND_USER_DN")

    @property
    def ldap_bind_secret(self):
        return os.environ.get("LDAP_BIND_PASS")

    @property
    def ldap_authorized_group(self):
        return os.environ.get("LDAP_AUTHORIZED_GROUP")

    @property
    def ldap_fallback_domain(self):
        return os.environ.get("LDAP_FALLBACK_DOMAIN", "example.com")

    @property
    def allowed_origins_raw(self):
        return os.environ.get("ALLOWED_ORIGINS")

    @property
    def allowed_origins(self):
        return os.environ.get("ALLOWED_ORIGINS", "*")

    @property
    def bypass_auth_for_testing(self):
        return os.environ.get("BYPASS_AUTH_FOR_TESTING") == "true"

    @property
    def data_dir(self):
        return os.environ.get("DATA_DIR", "/data")

    @property
    def skip_multiplexer(self):
        return os.environ.get("SKIP_MULTIPLEXER") == "true"

    @property
    def skip_preloader(self):
        return os.environ.get("SKIP_PRELOADER") == "true"

    @property
    def flask_debug(self):
        return os.environ.get("FLASK_DEBUG", "true").lower() == "true"

    @property
    def flask_use_reloader(self):
        return os.environ.get("FLASK_USE_RELOADER", "true").lower() == "true"

    @property
    def orphaned_session_ttl(self):
        val = os.environ.get("ORPHANED_SESSION_TTL")
        if val is not None:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    @property
    def port(self):
        return int(os.environ.get("PORT", 5000))

    @property
    def ui_port(self):
        return int(os.environ.get("UI_PORT", self.port))

    @property
    def api_port(self):
        return int(os.environ.get("API_PORT", 5002))

    @property
    def secret_key(self):
        return os.environ.get("SECRET_KEY")


env_config = EnvConfig()

logger = logging.getLogger(__name__)


def get_config_paths(data_dir=None):
    data_dir = data_dir or env_config.data_dir
    data_writable = os.access(
        data_dir if os.path.exists(data_dir) else os.path.dirname(data_dir.rstrip("/")),
        os.W_OK,
    )

    if not data_writable:
        if os.access("/tmp", os.W_OK):
            data_dir = "/tmp/gemini-data"
            os.makedirs(data_dir, exist_ok=True)
        else:
            logger.warning(
                "CRITICAL: No writable storage found (/data and /tmp are RO). Functionality will be limited."
            )

    config_file = os.path.join(data_dir, "config.json")
    ssh_dir = os.path.join(data_dir, ".ssh")
    return data_dir, config_file, ssh_dir


def get_config(data_dir=None):
    data_dir, config_file, ssh_dir = get_config_paths(data_dir)
    conf = {
        "LDAP_SERVER": env_config.ldap_server,
        "LDAP_BASE_DN": env_config.ldap_base_dn,
        "LDAP_BIND_USER_DN": env_config.ldap_bind_user_dn,
        "LDAP_BIND_SECRET": env_config.ldap_bind_secret,
        "LDAP_AUTHORIZED_GROUP": env_config.ldap_authorized_group,
        "LDAP_FALLBACK_DOMAIN": env_config.ldap_fallback_domain,
        "ALLOWED_ORIGINS": env_config.allowed_origins,
        "DATA_WRITABLE": os.access(os.path.dirname(config_file), os.W_OK)
        if os.path.exists(os.path.dirname(config_file))
        else False,
        "TMP_WRITABLE": os.access("/tmp", os.W_OK),
        "HOSTS": [{"label": "local", "type": "local"}],
    }

    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                file_config = json.load(f)
                conf.update(file_config)
        except Exception as e:
            logger.error(f"Error loading config file: {e}")

    if not conf.get("host_id"):
        hostname = socket.gethostname()
        h_id = hashlib.sha512(hostname.encode()).hexdigest()[:4]
        conf["host_id"] = h_id
        if conf.get("DATA_WRITABLE"):
            try:
                with open(config_file, "w") as f:
                    json.dump(conf, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to persist host_id: {e}")

    return conf


class AppConfigManager:
    def __init__(self):
        self._config = {}
        self._data_dir = None
        self._config_file = None

    def init_config(self, data_dir=None):
        self._data_dir, self._config_file, _ = get_config_paths(data_dir)
        self._config = get_config(self._data_dir)

        import secrets

        secret_key = self._config.get("SECRET_KEY") or env_config.secret_key
        if not secret_key:
            secret_key = secrets.token_hex(32)
            if self._config.get("DATA_WRITABLE"):
                try:
                    self._config["SECRET_KEY"] = secret_key
                    with open(self._config_file, "w") as f:
                        json.dump(self._config, f, indent=4)
                    logger.info("Generated and persisted new fallback SECRET_KEY")
                except Exception as e:
                    logger.error(f"Failed to persist fallback SECRET_KEY: {e}")
            else:
                logger.warning(
                    "SECRET_KEY not found and storage not writable. Sessions will invalidate on restart."
                )
        self._config["SECRET_KEY"] = secret_key

    def get(self, key, default=None):
        if not self._config:
            self.init_config()
        return self._config.get(key, default)

    def set(self, key, value):
        if not self._config:
            self.init_config()
        self._config[key] = value

    @property
    def data(self):
        if not self._config:
            self.init_config()
        return self._config

    def persist_config(self):
        if self.get("DATA_WRITABLE"):
            try:
                with open(self._config_file, "w") as f:
                    json.dump(self._config, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to persist config: {e}")

    @property
    def admin_user(self):
        return self.get("ADMIN_USER", env_config.admin_user)

    @property
    def admin_secret(self):
        return self.get("ADMIN_SECRET", env_config.admin_secret)

    @property
    def ldap_server(self):
        return self.get("LDAP_SERVER", env_config.ldap_server)

    @property
    def ldap_base_dn(self):
        return self.get("LDAP_BASE_DN", env_config.ldap_base_dn)

    @property
    def ldap_bind_user_dn(self):
        return self.get("LDAP_BIND_USER_DN", env_config.ldap_bind_user_dn)

    @property
    def ldap_bind_secret(self):
        return self.get("LDAP_BIND_SECRET", env_config.ldap_bind_secret)

    @property
    def ldap_authorized_group(self):
        return self.get("LDAP_AUTHORIZED_GROUP", env_config.ldap_authorized_group)

    @property
    def ldap_fallback_domain(self):
        return self.get("LDAP_FALLBACK_DOMAIN", env_config.ldap_fallback_domain)

    @property
    def secret_key(self):
        return self.get("SECRET_KEY") or env_config.secret_key

    @property
    def data_dir(self):
        if not self._data_dir:
            self.init_config()
        return self._data_dir

    @property
    def ssh_dir(self):
        if not self._data_dir:
            self.init_config()
        _, _, ssh_dir = get_config_paths(self._data_dir)
        return ssh_dir


app_config = AppConfigManager()
