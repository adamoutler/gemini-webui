import os
import shutil
import socket
import datetime
import subprocess
import logging

logger = logging.getLogger(__name__)


def setup_environment(data_dir: str, ssh_dir: str):
    """
    Bootstraps the application environment:
    - Creates necessary directories
    - Fixes permissions if running under a volume mount
    - Generates instance SSH keys if missing
    - Manages symlink for .gemini in the home directory
    """
    # Try FS operations but don't crash if they fail (RO filesystem)
    try:
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        gemini_data = os.path.join(data_dir, ".gemini")
        os.makedirs(gemini_data, mode=0o700, exist_ok=True)

        # Fix permissions if volume mount made them root-owned
        current_uid = os.getuid()
        for path in [gemini_data, ssh_dir]:
            try:
                stat = os.stat(path)
                if stat.st_uid == 0:
                    try:
                        # Attempt to use the current user/group instead of hardcoded 'node'
                        shutil.chown(path, user=current_uid, group=os.getgid())
                        # Recursively fix if it was existing root data
                        for root, dirs, files in os.walk(path):
                            for d in dirs:
                                shutil.chown(
                                    os.path.join(root, d),
                                    user=current_uid,
                                    group=os.getgid(),
                                )
                            for f in files:
                                shutil.chown(
                                    os.path.join(root, f),
                                    user=current_uid,
                                    group=os.getgid(),
                                )
                    except (LookupError, PermissionError):
                        pass
            except Exception as e:
                logger.warning(f"Failed to fix permissions on {path}: {e}")

        # Generate instance SSH key if not exists
        key_path = os.path.join(ssh_dir, "id_ed25519")
        if not os.path.exists(key_path):
            try:
                hostname = socket.gethostname()
                datestr = datetime.datetime.now().strftime("%Y%m%d")
                comment = f"gemini-webui-{hostname}-{datestr}"
                logger.info(
                    f"Generating new instance SSH key with comment: {comment}..."
                )
                subprocess.run(
                    [
                        "ssh-keygen",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        key_path,
                        "-C",
                        comment,
                    ],
                    check=True,
                )
                try:
                    shutil.chown(key_path, user=current_uid, group=os.getgid())
                    shutil.chown(key_path + ".pub", user=current_uid, group=os.getgid())
                except (LookupError, PermissionError):
                    pass
                os.chmod(key_path, 0o600)
            except Exception as e:
                logger.warning(f"Failed to generate SSH key: {e}")
    except Exception as e:
        logger.warning(
            f"FS initialization partially failed (likely RO filesystem): {e}"
        )

    # Manage symlink in home directory if it exists and is writable
    try:
        home_dir = os.path.expanduser("~")
        if os.path.exists(home_dir) and os.access(home_dir, os.W_OK):
            home_gemini = os.path.join(home_dir, ".gemini")
            gemini_data = os.path.join(data_dir, ".gemini")
            if os.path.islink(home_gemini):
                if os.readlink(home_gemini) != gemini_data:
                    os.unlink(home_gemini)
                    os.symlink(gemini_data, home_gemini)
            elif not os.path.exists(home_gemini):
                os.symlink(gemini_data, home_gemini)
    except Exception as e:
        logger.warning(f"Failed to manage symlink for .gemini: {e}")
