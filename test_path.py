import os
import shlex

def get_remote_path(filename, ssh_dir):
    if not ssh_dir or ssh_dir == "~":
        remote_path = filename
    elif ssh_dir.startswith('~/'):
        remote_path = f"{ssh_dir[2:]}/{filename}"
    else:
        remote_path = os.path.join(ssh_dir, filename).replace('\\', '/')
    return remote_path

print(get_remote_path("foo.txt", ""))
print(get_remote_path("foo.txt", "~"))
print(get_remote_path("foo.txt", "~/docs"))
print(get_remote_path("foo.txt", "/var/www"))
print(shlex.quote(get_remote_path("foo.txt", "~/docs")))
