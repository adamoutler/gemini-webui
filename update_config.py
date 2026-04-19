import os

with open("src/config.py", "r") as f:
    content = f.read()

new_content = (
    content
    + """
import json
import logging
import socket
import hashlib

logger = logging.getLogger(__name__)

def get_config_paths(data_dir=None):
    data_dir = data_dir or env_config.DATA_DIR
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

def load_config(data_dir=None):
    data_dir, config_file, ssh_dir = get_config_paths(data_dir)
    conf = {
        "LDAP_SERVER": env_config.LDAP_SERVER,
        "LDAP_BASE_DN": env_config.LDAP_BASE_DN,
        "LDAP_BIND_USER_DN": env_config.LDAP_BIND_USER_DN,
        "LDAP_BIND_PASS": env_config.LDAP_BIND_PASS,
        "LDAP_AUTHORIZED_GROUP": env_config.LDAP_AUTHORIZED_GROUP,
        "LDAP_FALLBACK_DOMAIN": env_config.LDAP_FALLBACK_DOMAIN,
        "ALLOWED_ORIGINS": env_config.ALLOWED_ORIGINS,
        "DATA_WRITABLE": os.access(os.path.dirname(config_file), os.W_OK) if os.path.exists(os.path.dirname(config_file)) else False,
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
        self._config = load_config(self._data_dir)

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

app_config = AppConfigManager()
"""
)

with open("src/config.py", "w") as f:
    f.write(new_content)
