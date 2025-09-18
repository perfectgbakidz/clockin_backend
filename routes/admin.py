from flask import Blueprint, request, jsonify
from datetime import date, datetime, time as dt_time
from sqlalchemy import func, distinct
from database import db
from models import User, AttendanceRecord
from routes.auth import roles_required

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

# ---------------- Dashboard ---------------- #
@admin_bp.route("/dashboard", methods=["GET"])
@roles_required("admin")
def dashboard():
    today = date.today()

    # Count total active employees (case-insensitive)
    total_employees = db.session.query(func.count(User.id))\
        .filter(func.lower(User.status) == "active").scalar() or 0

    # Count users who have clocked in today
    present_today = db.session.query(func.count(distinct(AttendanceRecord.user_id)))\
        .filter(AttendanceRecord.date == today).scalar() or 0

    # Fetch all clock-ins for late calculation
    records_today = db.session.query(AttendanceRecord.clock_in)\
        .filter(AttendanceRecord.date == today, AttendanceRecord.clock_in.isnot(None)).all()

    late_count = 0
    cutoff = dt_time(9, 0, 0)
    for (clock_in,) in records_today:
        if clock_in:
            # handle datetime or string
            time_val = getattr(clock_in, "time", lambda: clock_in)()
            if time_val > cutoff:
                late_count += 1

    absent_today = max(total_employees - present_today, 0)

    return jsonify({
        "totalEmployees": int(total_employees),
        "presentToday": int(present_today),
        "absentToday": int(absent_today),
        "lateArrivals": int(late_count)
    }), 200

# ---------------- Attendance Logs ---------------- #
@admin_bp.route("/attendance-logs", methods=["GET"])
@roles_required("admin", "hr")
def attendance_logs():
    q_date = request.args.get("date")
    search = request.args.get("search", "").strip()
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
    except ValueError:
        return jsonify({"error": "page and per_page must be integers"}), 400
    page = max(page, 1)
    per_page = min(max(per_page, 1), 500)

    query = db.session.query(
        AttendanceRecord.id,
        AttendanceRecord.user_id,
        User.name.label("userName"),
        AttendanceRecord.date,
        AttendanceRecord.clock_in,
        AttendanceRecord.clock_out,
        AttendanceRecord.total_hours
    ).join(User, AttendanceRecord.user_id == User.id)

    if q_date:
        try:
            parsed = datetime.strptime(q_date, "%Y-%m-%d").date()
            query = query.filter(AttendanceRecord.date == parsed)
        except ValueError:
            return jsonify({"error": "Invalid date format (use YYYY-MM-DD)"}), 400

    if search:
        query = query.filter(User.name.ilike(f"%{search}%"))

    query = query.order_by(AttendanceRecord.date.desc(), User.name.asc())

    total = query.count()
    items = query.limit(per_page).offset((page - 1) * per_page).all()

    results = [{
        "id": str(rec.id),
        "userId": str(rec.user_id),
        "userName": rec.userName,
        "date": rec.date.isoformat() if rec.date else None,
        "clockIn": rec.clock_in.isoformat() if rec.clock_in else None,
        "clockOut": rec.clock_out.isoformat() if rec.clock_out else None,
        "totalHours": float(rec.total_hours) if rec.total_hours is not None else None
    } for rec in items]

    return jsonify({
        "meta": {"total": total, "page": page, "per_page": per_page},
        "data": results
    }), 200

# ---------------- Employee Management ---------------- #
@admin_bp.route("/employees", methods=["GET"])
@roles_required("admin", "hr")
def get_employees():
    employees = User.query.filter(User.role == "employee").all()
    return jsonify([{
        "id": str(emp.id),
        "name": emp.name,
        "email": emp.email,
        "department": emp.department,
        "status": emp.status.capitalize(),  # Always 'Active' or 'Inactive'
        "role": emp.role
    } for emp in employees]), 200

@admin_bp.route("/employees", methods=["POST"])
@roles_required("admin")
def create_employee():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    department = (data.get("department") or "General").strip()
    password = data.get("password") or "ChangeMe123!"
    status = (data.get("status") or "Active").capitalize()

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 409

    new_user = User(
        name=name,
        email=email,
        role="employee",
        department=department,
        status=status
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "Employee created", "id": str(new_user.id)}), 201

@admin_bp.route("/employees/<uuid:user_id>", methods=["PUT"])
@roles_required("admin")
def update_employee(user_id):
    user = User.query.get(user_id)
    if not user or user.role != "employee":
        return jsonify({"error": "Employee not found"}), 404

    data = request.get_json() or {}
    if "name" in data:
        user.name = data["name"]
    if "email" in data:
        if User.query.filter(User.email == data["email"], User.id != user_id).first():
            return jsonify({"error": "Email already in use"}), 400
        user.email = data["email"]
    if "department" in data:
        user.department = data["department"]
    if "status" in data:
        user.status = data["status"].capitalize()

    db.session.commit()
    return jsonify({"message": "Employee updated"}), 200

@admin_bp.route("/employees/<uuid:user_id>", methods=["DELETE"])
@roles_required("admin")
def delete_employee(user_id):
    user = User.query.get(user_id)
    if not user or user.role != "employee":
        return jsonify({"error": "Employee not found"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Employee deleted"}), 200
