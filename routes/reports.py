# routes/reports.py
from flask import Blueprint, request, jsonify, Response
from datetime import date, timedelta, datetime
import io, csv
from sqlalchemy import func
from database import db
from models import User, AttendanceRecord
from routes.auth import roles_required

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/absenteeism-trends", methods=["GET"])
@roles_required("admin", "hr")
def absenteeism_trends():
    """
    GET /api/reports/absenteeism-trends
    Returns present vs absent counts for the past 7 days (including today).
    """
    total_active = db.session.query(func.count(User.id)).filter(User.status == "Active").scalar() or 0
    results = []
    for days_ago in range(6, -1, -1):  # 6 days ago ... today
        day = date.today() - timedelta(days=days_ago)
        present = (
            db.session.query(func.count(func.distinct(AttendanceRecord.user_id)))
            .filter(AttendanceRecord.date == day)
            .scalar() or 0
        )
        results.append({
            "name": day.strftime("%a"),  # Mon, Tue, ...
            "Present": int(present),
            "Absent": int(max(total_active - present, 0))
        })
    return jsonify(results), 200


@reports_bp.route("/working-hours", methods=["GET"])
@roles_required("admin", "hr")
def working_hours():
    """
    GET /api/reports/working-hours
    Average total_hours per day for the last 7 days.
    """
    results = []
    for days_ago in range(6, -1, -1):
        day = date.today() - timedelta(days=days_ago)
        avg = (
            db.session.query(func.avg(AttendanceRecord.total_hours))
            .filter(AttendanceRecord.date == day, AttendanceRecord.total_hours.isnot(None))
            .scalar()
        )
        avg_val = float(round(avg, 2)) if avg is not None else None
        results.append({"name": day.strftime("%a"), "avgHours": avg_val})
    return jsonify(results), 200


@reports_bp.route("/download", methods=["GET"])
@roles_required("admin", "hr")
def download():
    """
    GET /api/reports/download?type=weekly|monthly
    Returns CSV file as attachment.
    """
    typ = request.args.get("type", "weekly").lower()
    if typ not in ("weekly", "monthly"):
        return jsonify({"error": "type must be 'weekly' or 'monthly'"}), 400

    if typ == "weekly":
        start = date.today() - timedelta(days=6)
    else:
        start = date.today() - timedelta(days=29)
    end = date.today()

    rows = (
        db.session.query(
            AttendanceRecord.date,
            AttendanceRecord.user_id,
            User.name,
            AttendanceRecord.clock_in,
            AttendanceRecord.clock_out,
            AttendanceRecord.total_hours
        )
        .join(User, AttendanceRecord.user_id == User.id)
        .filter(AttendanceRecord.date >= start, AttendanceRecord.date <= end)
        .order_by(AttendanceRecord.date.asc(), User.name.asc())
        .all()
    )

    # Build CSV
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["date", "user_id", "user_name", "clock_in", "clock_out", "total_hours"])
    for r in rows:
        cw.writerow([
            r.date.isoformat() if r.date else "",
            str(r.user_id),
            r.name,
            r.clock_in.isoformat() if r.clock_in else "",
            r.clock_out.isoformat() if r.clock_out else "",
            float(r.total_hours) if r.total_hours is not None else ""
        ])
    csv_content = si.getvalue()
    si.close()

    filename = f"{typ}_attendance_{start.isoformat()}_to_{end.isoformat()}.csv"
    resp = Response(csv_content, mimetype="text/csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
