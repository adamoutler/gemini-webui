import json
import os


def test_manifest_short_name_and_comment():
    """
    Test that manifest.json has the correct short_name.
    """
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
        manifest_data.get("short_name") == "Gemini WebUI"
    ), "short_name must be 'Gemini WebUI'"
