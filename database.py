# database.py
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

# Import inside functions later to avoid circular import
db = SQLAlchemy()
bcrypt = Bcrypt()


def init_db(app):
    """
    Initialize DB and Bcrypt with the Flask app.
    Call from create_app() in your application factory:
        from database import init_db
        init_db(app)
    """
    db.init_app(app)
    bcrypt.init_app(app)

    # Enable foreign key constraints in SQLite
    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        # Only for SQLite
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    # Create tables and seed default admin if needed
    with app.app_context():
        from models import User  # import here to avoid circular deps
        db.create_all()

        # Check if an admin already exists
        admin = User.query.filter_by(role="admin").first()
        if not admin:
            admin = User(
                name="System Admin",
                email="admin@pardeefoods.com",
                role="admin",
                department="Management",
                status="Active",
            )
            admin.set_password("Admin@123")  # default password
            db.session.add(admin)
            db.session.commit()
            app.logger.info("Default admin user created: admin@pardeefoods.com / Admin@123")
