import base64
import hashlib
import hmac
import json
import os
import time
from functools import wraps

from flask import request, jsonify, current_app, g

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000  # OWASP guidance for PBKDF2-HMAC-SHA256
TOKEN_LIFETIME_SECONDS = 3600


def _b64(data):
    return base64.b64encode(data).decode()


def hash_password(password):
    """Return 'algorithm$iterations$salt$hash'.

    The iteration count is stored with the hash, so it can be raised
    later without breaking existing users.
    """
    iterations = current_app.config.get("PBKDF2_ITERATIONS", DEFAULT_ITERATIONS)
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, iterations
    )
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password, stored_password):
    try:
        algorithm, iterations, salt_text, hash_text = stored_password.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = base64.b64decode(salt_text)
        stored_hash = base64.b64decode(hash_text)
        new_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(new_hash, stored_hash)


def _sign(encoded_payload):
    secret = current_app.config["SECRET_KEY"]
    return hmac.new(
        secret.encode(), encoded_payload.encode(), hashlib.sha256
    ).hexdigest()


def create_token(user_id, lifetime=TOKEN_LIFETIME_SECONDS):
    payload = {"user_id": user_id, "expires": int(time.time()) + lifetime}
    encoded_payload = (
        base64.urlsafe_b64encode(json.dumps(payload).encode())
        .decode()
        .rstrip("=")
    )
    return encoded_payload + "." + _sign(encoded_payload)


def decode_token(token):
    """Return the payload if the token is valid and not expired, else None."""
    try:
        encoded_payload, received_signature = token.split(".")

        if not hmac.compare_digest(received_signature, _sign(encoded_payload)):
            return None

        padding = "=" * (-len(encoded_payload) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(encoded_payload + padding)
        )

        if payload["expires"] < time.time():
            return None
        if not isinstance(payload["user_id"], int):
            return None

        return payload

    except (ValueError, KeyError, TypeError):
        return None


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")

        if not authorization.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401

        payload = decode_token(authorization.split(" ", 1)[1])

        if payload is None:
            return jsonify({"error": "Invalid or expired token"}), 401

        g.user_id = payload["user_id"]
        return function(*args, **kwargs)

    return wrapper
