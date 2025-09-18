# models.py
import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator, BLOB, String
from sqlalchemy import CheckConstraint, JSON
from database import db, bcrypt


# ---------- UUID Support for SQLite ----------
class GUID(TypeDecorator):
    """
    Platform-independent GUID/UUID type.
    Uses PostgreSQL UUID type, otherwise stores as string.
    """
    impl = String

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(value)


# ---------- Users Table ----------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(50),
        nullable=False,
        default="employee"
    )
    department = db.Column(db.String(255), nullable=False)
    status = db.Column(
        db.String(50),
        nullable=False,
        default="Active"
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(role.in_(["employee", "admin", "hr"]), name="check_role"),
        CheckConstraint(status.in_(["Active", "Inactive"]), name="check_status"),
    )

    # Password helpers
    def set_password(self, password: str):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)


# ---------- Attendance Records ----------
class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"

    id = db.Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    clock_in = db.Column(db.DateTime, nullable=False)
    clock_out = db.Column(db.DateTime, nullable=True)
    total_hours = db.Column(db.Numeric(4, 2), nullable=True)

    user = db.relationship("User", backref="attendance_records", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", name="unique_user_date"),
    )


# ---------- WebAuthn Credentials ----------
class WebAuthnCredential(db.Model):
    __tablename__ = "webauthn_credentials"

    id = db.Column(db.LargeBinary, primary_key=True)  # credential ID as byte array
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    public_key = db.Column(db.LargeBinary, nullable=False)  # COSE-encoded public key
    counter = db.Column(db.BigInteger, nullable=False, default=0)
    transports = db.Column(JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="webauthn_credentials", lazy=True)
