import os
import shlex
import subprocess
from src.services.process_engine import build_ssh_args, validate_ssh_target


def upload_to_remote(
    local_filepath: str, filename: str, ssh_target: str, ssh_dir: str, ssh_dir_path: str
) -> str:
    """
    Uploads a file to a remote SSH target and returns the final remote path.
    """
    if not validate_ssh_target(ssh_target):
        raise ValueError("Invalid SSH target")

    if not ssh_dir or ssh_dir == "~":
        remote_path = filename
    elif ssh_dir.startswith("~/"):
        remote_path = f"{ssh_dir[2:]}/{filename}"
    else:
        remote_path = os.path.join(ssh_dir, filename).replace("\\", "/")

    remote_dir = os.path.dirname(remote_path)
    port = None
    clean_target = ssh_target
    if ":" in ssh_target:
        parts = ssh_target.rsplit(":", 1)
        if parts[1].isdigit():
            clean_target = parts[0]
            port = parts[1]

    ssh_cmd_base = build_ssh_args(ssh_target, ssh_dir_path)
    if port:
        ssh_cmd_base.extend(["-p", port])

    scp_cmd_base = ["scp"] + build_ssh_args(ssh_target, ssh_dir_path)[1:]
    if port:
        scp_cmd_base.extend(["-P", port])

    if remote_dir:
        ssh_cmd = ssh_cmd_base + [
            "--",
            clean_target,
            f"mkdir -p {shlex.quote(remote_dir)}",
        ]
        res = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to create remote directory: {res.stderr}")

    scp_cmd = scp_cmd_base + ["--", local_filepath, f"{clean_target}:{remote_path}"]
    result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"SCP failed: {result.stderr}")

    verify_cmd = ssh_cmd_base + [
        "--",
        clean_target,
        f"ls {shlex.quote(remote_path)}",
    ]
    # codeql[py/command-line-injection] False positive: Args are passed securely.
    verify_res = subprocess.run(verify_cmd, capture_output=True, timeout=15)
    if verify_res.returncode != 0:
        raise RuntimeError(
            "SCP returned 0, but file verification failed on remote host."
        )

    path_cmd = ssh_cmd_base + [
        "--",
        clean_target,
        f"realpath {shlex.quote(remote_path)} 2>/dev/null || readlink -m {shlex.quote(remote_path)} 2>/dev/null || echo {shlex.quote(remote_path)}",
    ]
    # codeql[py/command-line-injection] False positive: Args are passed securely.
    path_res = subprocess.run(path_cmd, capture_output=True, text=True, timeout=15)
    if path_res.returncode == 0 and path_res.stdout.strip():
        return path_res.stdout.strip()

    return remote_path
