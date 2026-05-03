from functools import wraps
from flask import request, jsonify


def validate_json(*expected_args):
    """
    Decorator to ensure the incoming request is JSON and contains expected keys.
    """

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Missing JSON in request"}), 400

            data = request.get_json()
            missing = [arg for arg in expected_args if arg not in data]
            if missing:
                return jsonify(
                    {"error": f"Missing required JSON fields: {', '.join(missing)}"}
                ), 400

            return f(*args, **kwargs)

        return wrapped

    return decorator


def validate_json_schema(schema):
    """
    Decorator to ensure the incoming request matches a Marshmallow schema.
    """

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Missing JSON in request"}), 400

            data = request.get_json()
            errors = schema().validate(data)
            if errors:
                return jsonify({"error": "Validation failed", "messages": errors}), 400

            return f(*args, **kwargs)

        return wrapped

    return decorator
