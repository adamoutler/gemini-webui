import os
import json


def test_version_files_consistency(client):
    # 1. Read VERSION file
    version_file_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "VERSION"
    )
    assert os.path.exists(version_file_path), "VERSION file does not exist"

    with open(version_file_path, "r") as f:
        version = f.read().strip()

    assert version != "", "VERSION file is empty"

    # 2. Check UI response
    response = client.get("/")
    assert response.status_code == 200
    html_content = response.data.decode("utf-8")
    expected_footer = f'<div id="version-footer" style="position: fixed; bottom: 5px; right: 5px; font-size: 10px; color: rgba(255, 255, 255, 0.3); pointer-events: none; z-index: 9999; font-family: monospace;">v{version}</div>'

    # Check if the exact footer exists or just the version string in the footer context
    import re

    html_clean = re.sub(r"\s+", "", html_content)
    assert (
        f"v{version}</div>" in html_clean
    ), f"Version {version} not found in UI response footer"
    # 3. Check manifest.json
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "src",
        "static",
        "manifest.json",
    )
    assert os.path.exists(manifest_path), "manifest.json does not exist"

    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    assert (
        manifest_data.get("version") == version
    ), f"manifest.json version {manifest_data.get('version')} does not match VERSION file {version}"

    # 4. Check sw.js
    sw_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "src",
        "static",
        "sw.js",
    )
    assert os.path.exists(sw_path), "sw.js does not exist"

    with open(sw_path, "r") as f:
        sw_content = f.read()

    expected_cache_name_pattern1 = f"const CACHE_NAME = 'gemini-webui-v{version}';"
    expected_cache_name_pattern2 = f'const CACHE_NAME = "gemini-webui-v{version}";'
    assert (
        expected_cache_name_pattern1 in sw_content
        or expected_cache_name_pattern2 in sw_content
    ), f"CACHE_NAME with version {version} not found in sw.js"
