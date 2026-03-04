import json
import os

def test_manifest_short_name_and_comment():
    """
    Test that manifest.json has the correct short_name ('GemWebUI') 
    for mobile differentiation and contains a comment explaining it.
    """
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
        'src', 'static', 'manifest.json'
    )
    
    assert os.path.exists(manifest_path), "manifest.json does not exist"
    
    with open(manifest_path, 'r') as f:
        manifest_data = json.load(f)
        
    assert manifest_data.get('short_name') == "GemWebUI", "short_name must be 'GemWebUI' to differentiate from the native Gemini app on mobile"
    assert "_comment" in manifest_data, "manifest.json must have a comment explaining the short_name"
    assert "differentiate" in manifest_data["_comment"].lower(), "comment must explain the reasoning for the short_name"
