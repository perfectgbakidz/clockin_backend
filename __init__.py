from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import os

db = SQLAlchemy()
bcrypt = Bcrypt()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pardee_foods.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    CORS(app)
    db.init_app(app)
    bcrypt.init_app(app)

    from app.models import user, attendance, webauthn_credential
    with app.app_context():
        db.create_all()

    from app.routes import auth, attendance_routes, admin, webauthn_routes
    app.register_blueprint(auth.bp, url_prefix='/api/auth')
    app.register_blueprint(attendance_routes.bp, url_prefix='/api/attendance')
    app.register_blueprint(admin.bp, url_prefix='/api/admin')
    app.register_blueprint(webauthn_routes.bp, url_prefix='/api/webauthn')

    return app
