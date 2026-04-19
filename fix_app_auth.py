import re

with open("src/app.py", "r") as f:
    content = f.read()

# Replace global variable usage in auth
content = content.replace(
    "auth.username == ADMIN_USER and auth.password == ADMIN_PASS",
    "auth.username == app_config.ADMIN_USER and auth.password == app_config.ADMIN_PASS",
)

content = content.replace("if LDAP_SERVER:", "if app_config.LDAP_SERVER:")
content = content.replace("LDAP_SERVER,", "app_config.LDAP_SERVER,")
content = content.replace("LDAP_BASE_DN,", "app_config.LDAP_BASE_DN,")
content = content.replace("LDAP_BIND_USER_DN,", "app_config.LDAP_BIND_USER_DN,")
content = content.replace("LDAP_BIND_PASS,", "app_config.LDAP_BIND_PASS,")
content = content.replace("LDAP_AUTHORIZED_GROUP,", "app_config.LDAP_AUTHORIZED_GROUP,")
content = content.replace("LDAP_FALLBACK_DOMAIN,", "app_config.LDAP_FALLBACK_DOMAIN,")

with open("src/app.py", "w") as f:
    f.write(content)
