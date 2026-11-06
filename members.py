import re
from flask import Blueprint, jsonify, request
import db
import fines
bp = Blueprint('members',__name__)

def valid_email(value):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(value)) is not None

def valid_email_type(value):
    return value in ("student", "staff")

@bp.route("/members", methods=["GET"])
def list_members():
    conn = db.connect()
    rows = conn.execute("SELECT * FROM members").fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({"id": r[0], "name": r[1], "email": r[2], "type": r[3]})
    return jsonify(result)

@bp.route("/members/<int:member_id>", methods=["GET"])
def get_member(member_id):
    conn = db.connect()
    r = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    if r is None:
        return jsonify({"error": "member not found"}), 404
    return jsonify({"id": r[0], "name": r[1], "email": r[2], "type": r[3]})

@bp.route("/members", methods=["POST"])
def create_member():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    if not valid_email(data.get("email")):
        return jsonify({"error": "invalid email"}), 400
    member_type = data.get("type", "student")
    if not valid_email_type(member_type):
        return jsonify({"error": "type must be student or staff"}), 400
    conn = db.connect()
    existing = conn.execute("SELECT * FROM members WHERE email = ?", (data["email"],)).fetchone()
    if existing is not None:
        conn.close()
        return jsonify({"error": "email already registered"}), 409
    cur = conn.execute(
        "INSERT INTO members (name, email, type) VALUES (?, ?, ?)",
        (data["name"], data["email"], member_type),
    )
    conn.commit()
    r = conn.execute("SELECT * FROM members WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify({"id": r[0], "name": r[1], "email": r[2], "type": r[3]}), 201

@bp.route("/members/<int:member_id>/loans", methods=["GET"])
def member_loans(member_id):
    conn = db.connect()
    m = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if m is None:
        conn.close()
        return jsonify({"error": "member not found"}), 404
    rows = conn.execute("SELECT * FROM loans WHERE member_id = ?", (member_id,)).fetchall()
    conn.close()
    owed = 0
    open_loans = 0
    loans = []
    for loan in rows:
        if loan[4] == 0:
            open_loans += 1
            owed += fines.fine_for(loan[3])
        elif loan[6] == 0:
            owed += loan[5]
        loans.append(
            {
                "id": loan[0],
                "book_id": loan[1],
                "due_date": loan[3],
                "returned": bool(loan[4]),
                "fine": fines.money(loan[5]),
                "fine_paid": bool(loan[6]),
            }
        )
    if m[3] == "staff":
        remaining = 5 - open_loans
    else:
        remaining = 3 - open_loans
    return jsonify({"loans": loans, "total_owed": fines.money(owed), "loans_remaining": remaining})
