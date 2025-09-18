# routes/webauthn.py
from flask import Blueprint, request, jsonify, session, current_app, g
from routes.auth import jwt_required
from services.webauthn_service import WebAuthnService
from models import WebAuthnCredential

webauthn_bp = Blueprint("webauthn", __name__)

# Key to store challenge in session
CHALLENGE_SESSION_KEY = "webauthn_challenge"

@webauthn_bp.route("/register/begin", methods=["GET"])
@jwt_required
def register_begin():
    user = g.current_user
    options_json = WebAuthnService.start_registration(user)

    # Store the challenge in session for verification
    if isinstance(options_json, dict) and "challenge" in options_json:
        session[CHALLENGE_SESSION_KEY] = options_json["challenge"]

    return jsonify(options_json), 200


@webauthn_bp.route("/register/finish", methods=["POST"])
@jwt_required
def register_finish():
    user = g.current_user
    body = request.get_data(as_text=True)

    # Get expected challenge from session
    expected_challenge = session.get(CHALLENGE_SESSION_KEY)
    if not expected_challenge:
        return jsonify({"verified": False, "error": "Challenge not found in session"}), 400

    try:
        cred = WebAuthnService.finish_registration(user, body, expected_challenge)
    except Exception as exc:
        current_app.logger.exception("webauthn register failed")
        return jsonify({"verified": False, "error": str(exc)}), 400

    # Clear challenge after use
    session.pop(CHALLENGE_SESSION_KEY, None)

    return jsonify({
        "verified": True,
        "message": "Device registered successfully",
        "credential_id": cred.id.hex()
    }), 200


@webauthn_bp.route("/login/begin", methods=["GET"])
def login_begin():
    user_id = request.args.get("userId")
    if not user_id:
        return jsonify({"error": "userId query param required"}), 400

    from models import User
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    options_json = WebAuthnService.start_authentication(user)

    if isinstance(options_json, dict) and "challenge" in options_json:
        session[CHALLENGE_SESSION_KEY] = options_json["challenge"]

    return jsonify(options_json), 200


@webauthn_bp.route("/login/finish", methods=["POST"])
def login_finish():
    user_id = request.args.get("userId")
    if not user_id:
        return jsonify({"error": "userId query param required"}), 400

    from models import User
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    body = request.get_data(as_text=True)

    expected_challenge = session.get(CHALLENGE_SESSION_KEY)
    if not expected_challenge:
        return jsonify({"verified": False, "error": "Challenge not found in session"}), 400

    try:
        verification = WebAuthnService.finish_authentication(user, body, expected_challenge)
    except Exception as exc:
        current_app.logger.exception("webauthn auth failed")
        return jsonify({"verified": False, "error": str(exc)}), 400

    session.pop(CHALLENGE_SESSION_KEY, None)
    return jsonify({"verified": True, "message": "Verification successful"}), 200


@webauthn_bp.route("/registration-status", methods=["GET"])
@jwt_required
def registration_status():
    user = g.current_user
    exists = WebAuthnCredential.query.filter_by(user_id=user.id).first() is not None
    return jsonify({"isRegistered": bool(exists)}), 200
