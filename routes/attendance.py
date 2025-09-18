from flask import Blueprint, request, jsonify
from datetime import datetime, date
from sqlalchemy.exc import IntegrityError
from database import db
from models import AttendanceRecord, User

attendance_bp = Blueprint("attendance", __name__)


@attendance_bp.route("/clock-in", methods=["POST"])
def clock_in():
    data = request.get_json()
    user_id = data.get("user_id")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    record = AttendanceRecord(
        user_id=user.id,
        date=date.today(),
        clock_in=datetime.utcnow(),
    )

    try:
        db.session.add(record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Already clocked in today"}), 400

    return jsonify({"message": "Clock-in successful", "record_id": str(record.id)}), 201


@attendance_bp.route("/clock-out", methods=["POST"])
def clock_out():
    data = request.get_json()
    user_id = data.get("user_id")

    record = AttendanceRecord.query.filter_by(
        user_id=user_id, date=date.today()
    ).first()

    if not record:
        return jsonify({"error": "No clock-in record found for today"}), 404

    if record.clock_out:
        return jsonify({"error": "Already clocked out"}), 400

    record.clock_out = datetime.utcnow()
    # Compute total hours
    delta = record.clock_out - record.clock_in
    record.total_hours = round(delta.total_seconds() / 3600, 2)

    db.session.commit()
    return jsonify({"message": "Clock-out successful", "total_hours": str(record.total_hours)})
