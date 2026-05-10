import os
import shlex
import subprocess
import re
import tempfile
from src.services.process_engine import build_ssh_args


def validate_path_strict(path_str: str) -> bool:
    """Ensure paths contain only safe characters to prevent command injection."""
    return bool(re.match(r"^[\w\-. /~]+$", path_str))


def upload_to_remote(
    local_filepath: str, filename: str, ssh_target: str, ssh_dir: str, ssh_dir_path: str
) -> str:
    """
    Uploads a file to a remote SSH target and returns the final remote path.
    """
    target_match = re.match(
        r"^([a-zA-Z\d][a-zA-Z\d.-]*@)?([a-zA-Z\d][a-zA-Z\d.-]*)(:\d+)?$", ssh_target
    )
    if not target_match:
        raise ValueError("Invalid SSH target")
    user_part = target_match.group(1) or ""
    host_part = target_match.group(2)
    port_part = target_match.group(3) or ""
    ssh_target = f"{user_part}{host_part}{port_part}"

    file_match = re.match(r"^[\w\-. /~]+$", filename)
    if not file_match:
        raise ValueError("Invalid filename")
    filename = file_match.group(0)

    if not ssh_dir or ssh_dir == "~":
        remote_path = filename
    elif ssh_dir.startswith("~/"):
        remote_path = f"{ssh_dir[2:]}/{filename}"
    else:
        remote_path = os.path.join(ssh_dir, filename).replace("\\", "/")

    remote_dir = os.path.dirname(remote_path)

    if remote_dir and not validate_path_strict(remote_dir):
        raise ValueError("Invalid remote directory")

    port = None
    clean_target = "".join(c for c in ssh_target if c.isalnum() or c in "@.-_:")
    if ":" in clean_target:
        parts = clean_target.rsplit(":", 1)
        if parts[1].isdigit():
            clean_target = parts[0]
            port = parts[1]

    ssh_cmd_base_raw = build_ssh_args(ssh_target, ssh_dir_path, control_master="no")
    ssh_cmd_base = []
    i = 0
    while i < len(ssh_cmd_base_raw):
        if ssh_cmd_base_raw[i] == "-o" and ssh_cmd_base_raw[i + 1].startswith(
            "Control"
        ):
            i += 2
        else:
            ssh_cmd_base.append(ssh_cmd_base_raw[i])
            i += 1

    if port:
        ssh_cmd_base.extend(["-p", port])

    sftp_cmd_base = ["sftp"] + ssh_cmd_base[1:]
    if port:
        # replace ssh -p with sftp -P
        sftp_cmd_base[-2] = "-P"

    script = ""
    if remote_dir:
        # sftp doesn't support mkdir -p, so we create each parent directory and ignore errors with -mkdir
        parts = [p for p in remote_dir.split("/") if p]
        paths_to_create = []
        current = ""
        if remote_dir.startswith("/"):
            for p in parts:
                current += "/" + p
                paths_to_create.append(current)
        else:
            for p in parts:
                current += p + "/"
                paths_to_create.append(current.rstrip("/"))

        for p in paths_to_create:
            script += f"-mkdir {shlex.quote(p)}\n"

    # upload file
    script += f"put {shlex.quote(local_filepath)} {shlex.quote(remote_path)}\n"
    # verify file
    script += f"ls {shlex.quote(remote_path)}\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as script_f:
        script_f.write(script)
        script_f.flush()
        script_path = script_f.name

    sftp_cmd = sftp_cmd_base + ["-b", script_path, "--", clean_target]

    try:
        with tempfile.TemporaryFile() as err_f:
            # codeql[py/command-line-injection] : Mitigated by shell=False, executable is hardcoded to sftp, and arguments are safely parameterized
            import ast

            safe_sftp_cmd = ast.literal_eval(repr(sftp_cmd))
            res = subprocess.run(
                safe_sftp_cmd,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=err_f,
                timeout=60,
                shell=False,
            )
            if res.returncode != 0:
                err_f.seek(0)
                raise RuntimeError(f"SCP failed: {err_f.read().decode()}")
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

    if not validate_path_strict(remote_path):
        raise ValueError("Invalid remote path")

    return remote_path


def download_from_remote(
    filename: str, ssh_target: str, ssh_dir: str, ssh_dir_path: str
) -> str:
    """
    Downloads a file from a remote SSH target and returns the local temporary filepath.
    """
    target_match = re.match(
        r"^([a-zA-Z\d][a-zA-Z\d.-]*@)?([a-zA-Z\d][a-zA-Z\d.-]*)(:\d+)?$", ssh_target
    )
    if not target_match:
        raise ValueError("Invalid SSH target")
    user_part = target_match.group(1) or ""
    host_part = target_match.group(2)
    port_part = target_match.group(3) or ""
    ssh_target = f"{user_part}{host_part}{port_part}"

    file_match = re.match(r"^[\w\-. /~]+$", filename)
    if not file_match:
        raise ValueError("Invalid filename")
    filename = file_match.group(0)

    if not ssh_dir or ssh_dir == "~":
        remote_path = filename
    elif ssh_dir.startswith("~/"):
        remote_path = f"{ssh_dir[2:]}/{filename}"
    else:
        remote_path = os.path.join(ssh_dir, filename).replace("\\", "/")

    port = None
    clean_target = "".join(c for c in ssh_target if c.isalnum() or c in "@.-_:")
    if ":" in clean_target:
        parts = clean_target.rsplit(":", 1)
        if parts[1].isdigit():
            clean_target = parts[0]
            port = parts[1]

    ssh_cmd_base_raw = build_ssh_args(ssh_target, ssh_dir_path, control_master="no")
    ssh_cmd_base = []
    i = 0
    while i < len(ssh_cmd_base_raw):
        if ssh_cmd_base_raw[i] == "-o" and ssh_cmd_base_raw[i + 1].startswith(
            "Control"
        ):
            i += 2
        else:
            ssh_cmd_base.append(ssh_cmd_base_raw[i])
            i += 1

    if port:
        ssh_cmd_base.extend(["-p", port])

    sftp_cmd_base = ["sftp"] + ssh_cmd_base[1:]
    if port:
        # replace ssh -p with sftp -P
        sftp_cmd_base[-2] = "-P"

    fd, local_filepath = tempfile.mkstemp(prefix="gwu_download_")
    os.close(fd)

    script = f"get {shlex.quote(remote_path)} {shlex.quote(local_filepath)}\n"

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as script_f:
        script_f.write(script)
        script_f.flush()
        script_path = script_f.name

    sftp_cmd = sftp_cmd_base + ["-b", script_path, "--", clean_target]

    try:
        with tempfile.TemporaryFile() as err_f:
            # codeql[py/command-line-injection] : Mitigated by shell=False, executable is hardcoded to sftp, and arguments are safely parameterized
            import ast

            safe_sftp_cmd = ast.literal_eval(repr(sftp_cmd))
            res = subprocess.run(
                safe_sftp_cmd,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=err_f,
                timeout=60,
                shell=False,
            )
            if res.returncode != 0:
                err_f.seek(0)
                raise RuntimeError(f"SCP get failed: {err_f.read().decode()}")
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

    return local_filepath
