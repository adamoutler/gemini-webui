import os


class EnvConfig:
    @property
    def SKIP_MONKEY_PATCH(self):
        return os.environ.get("SKIP_MONKEY_PATCH") == "true"

    @property
    def GEMINI_BIN(self):
        return os.environ.get("GEMINI_BIN", "gemini")

    @property
    def ADMIN_USER(self):
        return os.environ.get("ADMIN_USER", "admin")

    @property
    def ADMIN_PASS(self):
        return os.environ.get("ADMIN_PASS", "admin")

    @property
    def LDAP_SERVER(self):
        return os.environ.get("LDAP_SERVER")

    @property
    def LDAP_BASE_DN(self):
        return os.environ.get("LDAP_BASE_DN")

    @property
    def LDAP_BIND_USER_DN(self):
        return os.environ.get("LDAP_BIND_USER_DN")

    @property
    def LDAP_BIND_PASS(self):
        return os.environ.get("LDAP_BIND_PASS")

    @property
    def LDAP_AUTHORIZED_GROUP(self):
        return os.environ.get("LDAP_AUTHORIZED_GROUP")

    @property
    def LDAP_FALLBACK_DOMAIN(self):
        return os.environ.get("LDAP_FALLBACK_DOMAIN", "example.com")

    @property
    def ALLOWED_ORIGINS_RAW(self):
        return os.environ.get("ALLOWED_ORIGINS")

    @property
    def ALLOWED_ORIGINS(self):
        return os.environ.get("ALLOWED_ORIGINS", "*")

    @property
    def BYPASS_AUTH_FOR_TESTING(self):
        return os.environ.get("BYPASS_AUTH_FOR_TESTING") == "true"

    @property
    def DATA_DIR(self):
        return os.environ.get("DATA_DIR", "/data")

    @property
    def SKIP_MULTIPLEXER(self):
        return os.environ.get("SKIP_MULTIPLEXER") == "true"

    @property
    def SKIP_PRELOADER(self):
        return os.environ.get("SKIP_PRELOADER") == "true"

    @property
    def FLASK_DEBUG(self):
        return os.environ.get("FLASK_DEBUG", "true").lower() == "true"

    @property
    def FLASK_USE_RELOADER(self):
        return os.environ.get("FLASK_USE_RELOADER", "true").lower() == "true"

    @property
    def PORT(self):
        return int(os.environ.get("PORT", 5000))

    @property
    def SECRET_KEY(self):
        return os.environ.get("SECRET_KEY")


env_config = EnvConfig()
