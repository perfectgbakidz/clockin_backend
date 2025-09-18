# routes/employees.py
from flask import Blueprint, jsonify
from models import User
from routes.auth import roles_required, user_summary

employees_bp = Blueprint("employees", __name__)

@employees_bp.route("/admin/employees", methods=["GET"])
@roles_required("admin", "hr")
def list_employees():
    employees = User.query.filter_by(role="employee").all()
    return jsonify([user_summary(u) for u in employees]), 200
