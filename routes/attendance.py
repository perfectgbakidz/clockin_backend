from flask import Blueprint, request, jsonify
from datetime import datetime, date
from sqlalchemy.exc import IntegrityError
from database import db
from models import AttendanceRecord, User

attendance_bp = Blueprint("attendance", __name__)

# ---------------- CORS preflight helper ----------------
@attendance_bp.before_request
def handle_options():
    if request.method == "OPTIONS":
        # Respond 200 for preflight
        return '', 200

# ---------------- Clock-in ----------------
@attendance_bp.route("/clock-in", methods=["POST", "OPTIONS"])
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

# ---------------- Clock-out ----------------
@attendance_bp.route("/clock-out", methods=["POST", "OPTIONS"])
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

# ---------------- Attendance history (example GET) ----------------
@attendance_bp.route("/history", methods=["GET", "OPTIONS"])
def attendance_history():
    if request.method == "OPTIONS":
        return '', 200  # Preflight response

    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    records = AttendanceRecord.query.filter_by(user_id=user_id).order_by(AttendanceRecord.date.desc()).all()
    data = [
        {
            "date": r.date.isoformat(),
            "clock_in": r.clock_in.isoformat(),
            "clock_out": r.clock_out.isoformat() if r.clock_out else None,
            "total_hours": str(r.total_hours) if r.total_hours else None
        }
        for r in records
    ]
    return jsonify(data), 200
