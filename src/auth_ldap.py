try:
    from config import env_config
except ImportError:
    pass
import ldap3
from ldap3.utils.conv import escape_filter_chars
import logging

logger = logging.getLogger(__name__)


def sanitize_ldap_input(input_str):
    return escape_filter_chars(str(input_str)) if input_str else ""


def check_auth(
    username,
    password,
    ldap_server,
    ldap_base_dn,
    ldap_bind_user_dn=None,
    ldap_bind_pass=None,
    ldap_authorized_group=None,
    ldap_fallback_domain=None,
):
    try:
        safe_username = sanitize_ldap_input(username)
        server = ldap3.Server(ldap_server, get_info=ldap3.ALL, connect_timeout=2)

        if ldap_bind_user_dn and ldap_bind_pass:
            conn = ldap3.Connection(
                server, user=ldap_bind_user_dn, password=ldap_bind_pass, auto_bind=True
            )
            search_filter = f"(&(objectClass=*)(sAMAccountName={safe_username}))"
            conn.search(ldap_base_dn, search_filter, attributes=["memberOf"])

            if not conn.entries:
                return False

            user_entry = conn.entries[0]
            user_dn = user_entry.entry_dn

            if ldap_authorized_group:
                member_of = user_entry["memberOf"] if "memberOf" in user_entry else []
                group_match = any(
                    ldap_authorized_group.lower() in group.lower()
                    for group in member_of
                )
                if not group_match:
                    return False

            ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
            return True
        else:
            user_dn = f"{username}@{ldap_fallback_domain}"
            ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
            return True

    except Exception as e:
        logger.error(f"LDAP Error: {e}")
        return False
