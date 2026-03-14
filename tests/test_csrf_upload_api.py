import re
from io import BytesIO
from src.app import app


def test_csrf_upload(client):
    app.config["WTF_CSRF_ENABLED"] = True

    # Get the token
    response = client.get("/")
    match = re.search(
        r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"',
        response.data.decode("utf-8"),
    )
    assert match is not None
    csrf_token = match.group(1)

    # Try upload
    data = {"file": (BytesIO(b"my file contents"), "test.txt")}

    response = client.post(
        "/api/upload",
        data=data,
        content_type="multipart/form-data",
        headers={"X-CSRFToken": csrf_token},
    )
    print("STATUS:", response.status_code)
    print("DATA:", response.data)

    app.config["WTF_CSRF_ENABLED"] = False
