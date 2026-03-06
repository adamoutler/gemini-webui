import re

with open('src/app.py', 'r') as f:
    content = f.read()

# L60
content = content.replace(
'''try:
    with open("VERSION", "r") as f:
        APP_VERSION = f.read().strip()
except Exception:
    APP_VERSION = "unknown"''',
'''try:
    with open("VERSION", "r") as f:
        APP_VERSION = f.read().strip()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Failed to read VERSION: {e}")
    APP_VERSION = "unknown"''')

# L166
content = content.replace(
'''                        for f in files: shutil.chown(os.path.join(root, f), user='node', group='node')
            except Exception: pass''',
'''                        for f in files: shutil.chown(os.path.join(root, f), user='node', group='node')
            except Exception as e:
                logger.warning(f"Failed to fix permissions on {path}: {e}")''')

# L180
content = content.replace(
'''                shutil.chown(key_path + '.pub', user='node', group='node')
                os.chmod(key_path, 0o600)
            except Exception: pass''',
'''                shutil.chown(key_path + '.pub', user='node', group='node')
                os.chmod(key_path, 0o600)
            except Exception as e:
                logger.warning(f"Failed to generate SSH key: {e}")''')

# L195
content = content.replace(
'''        elif not os.path.exists(home_gemini):
            os.makedirs(os.path.dirname(home_gemini), exist_ok=True)
            os.symlink(gemini_data, home_gemini)
    except Exception: pass''',
'''        elif not os.path.exists(home_gemini):
            os.makedirs(os.path.dirname(home_gemini), exist_ok=True)
            os.symlink(gemini_data, home_gemini)
    except Exception as e:
        logger.warning(f"Failed to manage symlink for {home_gemini}: {e}")''')

# L424
content = content.replace(
'''        try:
            set_winsize(session_obj.fd, data['rows'], data['cols'])
        except Exception:
            pass''',
'''        try:
            set_winsize(session_obj.fd, data['rows'], data['cols'])
        except Exception as e:
            logger.warning(f"Failed to set winsize on fd {session_obj.fd}: {e}")''')

# L455
content = content.replace(
'''            # Re-sync terminal size
            try:
                set_winsize(session_obj.fd, data.get('rows', 24), data.get('cols', 80))
            except Exception: pass''',
'''            # Re-sync terminal size
            try:
                set_winsize(session_obj.fd, data.get('rows', 24), data.get('cols', 80))
            except Exception as e:
                logger.warning(f"Failed to set winsize on fd {session_obj.fd}: {e}")''')

# L484
content = content.replace(
'''            session_manager.remove_session(oldest_session.tab_id)
            try:
                os.kill(oldest_session.pid, signal.SIGKILL)
                os.waitpid(oldest_session.pid, 0)
            except Exception: pass''',
'''            session_manager.remove_session(oldest_session.tab_id)
            try:
                os.kill(oldest_session.pid, signal.SIGKILL)
                os.waitpid(oldest_session.pid, 0)
            except Exception as e:
                logger.warning(f"Failed to kill evicted session {oldest_session.pid}: {e}")''')

# L493
content = content.replace(
'''    if old_session:
        logger.info(f"Killing old session {tab_id} for fresh restart")
        try:
            os.kill(old_session.pid, signal.SIGKILL)
            os.waitpid(old_session.pid, 0)
        except Exception: pass''',
'''    if old_session:
        logger.info(f"Killing old session {tab_id} for fresh restart")
        try:
            os.kill(old_session.pid, signal.SIGKILL)
            os.waitpid(old_session.pid, 0)
        except Exception as e:
            logger.warning(f"Failed to kill old session {old_session.pid}: {e}")''')

# L534
content = content.replace(
'''        try: set_winsize(fd, rows, cols)
        except Exception: pass''',
'''        try: set_winsize(fd, rows, cols)
        except Exception as e: logger.warning(f"Failed to set winsize on fd {fd}: {e}")''')

with open('src/app.py', 'w') as f:
    f.write(content)
