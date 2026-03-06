# Improve assertions in test_api.py

## Details of what's required
The `test_api.py` file currently contains several tests with weak assertions. Many of the JSON validation tests only check the HTTP status code (e.g., `assert response.status_code == 200`) and the presence of certain keys (e.g., `'status' in response.json`), but fail to check the actual expected values of those keys. 

Specific areas to address:
- `test_api_health`: Ensure that we validate the exact value of the `status` key (e.g., `'status': 'ok'`) instead of just checking for its presence.
- `test_api_keys_list`: Ensure that the result is not only a list but that the elements inside the list conform to the expected schema or have the expected properties.
- `test_api_keys_public`: The test currently allows for either a 200 or 404 response. This is overly permissive and can mask regressions if key generation silently fails. Mock the underlying state or provide appropriate fixtures to ensure deterministic 200 or 404 behavior, and assert exactly one of them depending on the scenario.
- Review all other tests in `test_api.py` and replace any shallow assertions with deep equality checks where possible.

## Test recommendations
- Run `pytest tests/test_api.py` after modifications to ensure everything passes.
- Temporarily mutate the application code (e.g., return a wrong status string) to ensure your new assertions correctly catch the failure.
- Ensure that you are using exact literal matching for expected response values.

## Definition of Done
- All API tests in `test_api.py` assert both the status code and the exact values in the JSON response payload.
- Permissive checks (like allowing multiple status codes for a single test path) have been eliminated in favor of deterministic tests.
- `pytest tests/test_api.py` passes completely.
- `pytest tests/` runs without errors caused by these changes.