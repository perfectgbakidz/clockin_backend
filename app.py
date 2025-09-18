# app.py
import os
from flask import Flask, jsonify
from flask_cors import CORS

# Local imports
from database import init_db, db
import models  # noqa: F401

def create_app(test_config: dict = None):
    app = Flask(__name__, instance_relative_config=False)

    # --- SECRET KEY: required for session support (WebAuthn) ---
    secret = os.environ.get("SECRET_KEY", "dev_secret_key_change_me")
    app.secret_key = secret
    app.config["SECRET_KEY"] = secret

    # --- Database configuration ---
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        os.environ.get("DATABASE_URL", "sqlite:///attendance.db")
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    # --- Apply CORS ---
    CORS(
        app,
        origins=["https://clockin-pi.vercel.app"],  # your frontend URL
        supports_credentials=True,
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )

    # --- Apply test configuration if provided ---
    if test_config:
        app.config.update(test_config)

    # --- Initialize database ---
    init_db(app)

    # --- Import and register blueprints ---
    from routes.auth import auth_bp
    from routes.attendance import attendance_bp
    from routes.admin import admin_bp
    from routes.reports import reports_bp
    from routes.webauthn import webauthn_bp
    from routes.employees import employees_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(attendance_bp, url_prefix="/api/attendance")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(webauthn_bp, url_prefix="/api/webauthn")
    app.register_blueprint(employees_bp, url_prefix="/api")

    # --- Health check route ---
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "app": "pardee-foods-backend"})

    return app

# --- Only create the app once ---
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
