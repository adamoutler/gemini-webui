# src/decorators Module

## Purpose

The `src/decorators` module is a dedicated space for cross-cutting concerns, currently focused primarily on request validation for the application's REST API. It implements the project's "Paranoid Input Validation" security mandate by providing declarative decorators that check for JSON presence, required keys, and schema compliance. It acts as a gatekeeper, ensuring that route handlers only process well-formed and valid data.

## General Themes

- **Declarative Security**: Shifts validation logic out of the route handlers and into reusable decorators, ensuring consistent enforcement.
- **Fail-Fast Mechanism**: Rejects malformed or invalid requests immediately, before any core business logic or external service calls are executed.
- **Consistent Error Reporting**: Standardizes the format of validation error responses across the API.
- **Centralization (Future Goal)**: While authentication decorators (`authenticated_only`, `api_key_required`) currently reside in `src/auth.py` and `src/routes/auth_utils.py`, the architectural pattern suggests they should eventually be centralized here to unify all request interception logic.

## Module Contracts & APIs

### `validation.py`

This file contains the core request validation logic.

- **`validate_json(required_keys=None)`**

  - **Contract**: Ensures the incoming request is properly formatted JSON. Optionally checks for the presence of specific top-level keys.
  - **Behavior**:
    - Returns `400 Bad Request` if the `Content-Type` is not `application/json` or if the JSON payload is malformed.
    - Returns `400 Bad Request` if any key in `required_keys` is missing from the payload.
  - **Usage**: Applied to API routes (e.g., in `src/routes/api.py`) that expect simple JSON payloads.

- **`validate_json_schema(schema_class)`**
  - **Contract**: Validates the incoming JSON payload against a defined Marshmallow schema (`schema_class`).
  - **Behavior**:
    - Instantiates the provided `schema_class`.
    - Uses the schema to load and validate the request JSON.
    - If validation fails, returns a `400 Bad Request` with detailed error messages explaining which fields failed validation.
    - If validation succeeds, passes the parsed/validated data to the decorated route handler as a keyword argument (usually `data`).
  - **Usage**: Applied to complex API routes where strict type checking, format validation, and data sanitization are required.

## Internal Dependencies

- **`marshmallow`**: Used extensively by `validate_json_schema` for defining and enforcing schemas.
- **`flask`**: Uses `request` and `jsonify` to inspect incoming HTTP requests and format error responses.

## External Dependencies

- **`src/routes/api.py`**: The primary consumer of these decorators, applying them to endpoints like `/api/prompts` and `/api/tasks`.
