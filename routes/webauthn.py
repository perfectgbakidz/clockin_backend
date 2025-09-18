# routes/webauthn.py
from flask import Blueprint, request, jsonify, session, current_app, g
from routes.auth import jwt_required
from services.webauthn_service import WebAuthnService
from models import WebAuthnCredential

webauthn_bp = Blueprint("webauthn", __name__)

# NOTE: for production you should store the challenge server-side in a short-lived store (Redis)
# Here we use Flask session for simplicity (not ideal for multiple backend instances).
CHALLENGE_SESSION_KEY = "webauthn_challenge"

@webauthn_bp.route("/register/begin", methods=["GET"])
@jwt_required
def register_begin():
    user = g.current_user
    options_json = WebAuthnService.start_registration(user)
    # store the challenge in session (the webauthn library will include challenge in options)
    # libraries differ; adjust if your options_json contains the raw challenge field
    session[CHALLENGE_SESSION_KEY] = options_json.get("challenge") if isinstance(options_json, dict) else None
    return jsonify(options_json), 200


@webauthn_bp.route("/register/finish", methods=["POST"])
@jwt_required
def register_finish():
    user = g.current_user
    body = request.get_data(as_text=True)
    # developer: verify stored challenge here (omitted depending on webauthn lib)
    try:
        cred = WebAuthnService.finish_registration(user, body)
    except Exception as exc:
        current_app.logger.exception("webauthn register failed")
        return jsonify({"verified": False, "error": str(exc)}), 400
    return jsonify({"verified": True, "message": "Device registered successfully", "credential_id": cred.id.hex()}), 200


@webauthn_bp.route("/login/begin", methods=["GET"])
def login_begin():
    """
    This endpoint is called by the popup before navigator.credentials.get()
    Query param: userId (optional) — if omitted, the currently signed-in user is expected.
    """
    user_id = request.args.get("userId")
    # If userId provided, you might look up the user and create options for them.
    # For simplicity we expect client to call this from authenticated context (or pass userId)
    # Here we return an error if userId not provided.
    if not user_id:
        return jsonify({"error": "userId query param required"}), 400

    from models import User
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    options_json = WebAuthnService.start_authentication(user)
    session[CHALLENGE_SESSION_KEY] = options_json.get("challenge") if isinstance(options_json, dict) else None
    return jsonify(options_json), 200


@webauthn_bp.route("/login/finish", methods=["POST"])
def login_finish():
    """
    The final verification endpoint: client sends the assertion here.
    Expect body to be the raw JSON from navigator.credentials.get() result.
    Query param: userId is required to find the credential.
    """
    user_id = request.args.get("userId")
    if not user_id:
        return jsonify({"error": "userId query param required"}), 400

    from models import User
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    body = request.get_data(as_text=True)
    try:
        verification = WebAuthnService.finish_authentication(user, body)
    except Exception as exc:
        current_app.logger.exception("webauthn auth failed")
        return jsonify({"verified": False, "error": str(exc)}), 400

    return jsonify({"verified": True, "message": "Verification successful"}), 200


@webauthn_bp.route("/registration-status", methods=["GET"])
@jwt_required
def registration_status():
    user = g.current_user
    exists = WebAuthnCredential.query.filter_by(user_id=user.id).first() is not None
    return jsonify({"isRegistered": bool(exists)}), 200
