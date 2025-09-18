from functools import wraps
from datetime import datetime, timedelta
import jwt

from flask import Blueprint, request, jsonify, current_app, g

from database import db
from models import User

auth_bp = Blueprint("auth", __name__)

# ---------------- JWT helpers ---------------- #
def _jwt_secret() -> str:
    secret = current_app.config.get("SECRET_KEY")
    if not secret or not isinstance(secret, str):
        return "dev_secret_key_change_me"
    return secret

def create_jwt_token(user_id: str, role: str, expires_in_seconds: int = None) -> str:
    expires_in = expires_in_seconds or current_app.config.get("JWT_EXP_DELTA_SECONDS", 60 * 60 * 2)
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=current_app.config.get("JWT_ALGORITHM", "HS256"))
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token

def decode_jwt_token(token: str):
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[current_app.config.get("JWT_ALGORITHM", "HS256")])
        return payload
    except jwt.ExpiredSignatureError:
        return {"error": "token_expired"}
    except jwt.InvalidTokenError:
        return {"error": "invalid_token"}

# ---------------- Decorators ---------------- #
def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"error": "Authorization header required"}), 401
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "Invalid Authorization header format. Use: Bearer <token>"}), 401

        token = parts[1]
        payload = decode_jwt_token(token)
        if "error" in payload:
            return jsonify({"error": "Token expired" if payload["error"] == "token_expired" else "Invalid token"}), 401

        user_id = payload.get("sub")
        user = User.query.filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 401
        if user.status != "Active":
            return jsonify({"error": "User inactive"}), 403

        g.current_user = user
        g.jwt_payload = payload
        return f(*args, **kwargs)
    return decorated

def roles_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        @jwt_required
        def decorated(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            if user.role not in allowed_roles:
                return jsonify({"error": "Forbidden - insufficient role"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ---------------- Utilities ---------------- #
def user_summary(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "department": user.department,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if getattr(user, "updated_at", None) else None,
    }

@auth_bp.route("/admin/create", methods=["POST"])
def create_admin():
    """
    Endpoint to create a new admin user.
    - If no admins exist yet, anyone can create the first admin.
    - After that, only existing admins can create new admins.
    """
    # Check if any admins exist
    existing_admin = User.query.filter_by(role="admin").first()

    # If admins exist, require JWT and admin role
    if existing_admin:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"error": "Authorization header required"}), 401
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "Invalid Authorization header format. Use: Bearer <token>"}), 401
        token = parts[1]
        payload = decode_jwt_token(token)
        if "error" in payload:
            return jsonify({"error": "Token expired" if payload["error"] == "token_expired" else "Invalid token"}), 401
        user_id = payload.get("sub")
        user = User.query.filter_by(id=user_id).first()
        if not user or user.role != "admin":
            return jsonify({"error": "Only admins can create new admins"}), 403

    # Get input data
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or "Admin123!"

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User with that email already exists"}), 409

    # Create admin
    new_admin = User(
        name=name,
        email=email,
        role="admin",
        department="Management",
        status="Active"
    )
    new_admin.set_password(password)
    db.session.add(new_admin)
    db.session.commit()

    return jsonify({"message": "Admin created successfully", "user": user_summary(new_admin)}), 201


# ---------------- Routes ---------------- #
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401
    if user.status != "Active":
        return jsonify({"error": "Account inactive"}), 403

    token = create_jwt_token(str(user.id), user.role)
    return jsonify({"token": token, "user": user_summary(user)}), 200

@auth_bp.route("/change-password", methods=["POST"])
@jwt_required
def change_password():
    data = request.get_json() or {}
    old = data.get("oldPassword")
    new = data.get("newPassword")
    if not old or not new:
        return jsonify({"error": "oldPassword and newPassword required"}), 400

    user: User = g.current_user
    if not user.check_password(old):
        return jsonify({"error": "Old password is incorrect"}), 400
    if len(new) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400

    user.set_password(new)
    db.session.commit()
    return jsonify({"message": "Password updated successfully"}), 200

@auth_bp.route("/admin/employees", methods=["POST"])
@roles_required("admin")
def create_employee():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or "ChangeMe123!"
    role = (data.get("role") or "employee").strip().lower()
    department = (data.get("department") or "General").strip()
    status = (data.get("status") or "Active").capitalize()

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User with that email already exists"}), 409
    if role not in ("employee", "admin", "hr"):
        return jsonify({"error": "Invalid role"}), 400
    if status not in ("Active", "Inactive"):
        return jsonify({"error": "Invalid status"}), 400

    new_user = User(
        name=name, email=email, role=role, department=department, status=status
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"user": user_summary(new_user)}), 201

@auth_bp.route("/users", methods=["GET"])
@roles_required("admin", "hr")
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([user_summary(u) for u in users]), 200

