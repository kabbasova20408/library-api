from datetime import date, timedelta
from flask import Blueprint, jsonify, request
import db
import fines

bp= Blueprint("loans",__name__)

def valid_date(value):
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False

def send_email(email,subject,body):
    with open("outbox.txt", "a") as f:
            f.write("TO: " + email + " | SUBJECT: " + subject + " | BODY: " + body + "\n")

def loan_json(loan):
     return{
         "id": loan[0],
         "book_id": loan[1],
         "member_id": loan[2],
         "due_date": loan[3],
         "returned": bool(loan[4]),
         "fine": fines.money(loan[5]),
         "fine_paid": bool(loan[6]),
         "renewals": loan[7],
         "checked_out": loan[8],
        }
def loan_detail_json(loan):
    current_fine = loan[5]
    if loan[4] == 0:
        current_fine = fines.fine_for(loan[3])
    result = loan_json(loan)
    result['current_fine'] = fines.money(current_fine)
    return result

@bp.route("/loans", methods=["GET"])
def list_loans():
    conn = db.connect()
    rows = conn.execute("SELECT * FROM loans").fetchall()
    conn.close()
    result = []
    for loan in rows:
        current_fine = loan[5]
        days_late = fines.days_late(loan[3])
        if request.args.get("overdue") == "true" and (loan[4] == 1 or days_late <= 0):
            continue
        result.append(loan_detail_json(loan))
    return jsonify(result)

@bp.route("/loans/<int:loan_id>", methods=["GET"])
def get_loan(loan_id):
    conn = db.connect()
    loan = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    conn.close()
    if loan is None:
        return jsonify({"error": "loan not found"}), 404
    return jsonify(loan_detail_json(loan))

@bp.route("/loans", methods=["POST"])
def create_loan():
    data = request.get_json(silent=True) or {}
    if not data.get("book_id") or not data.get("member_id"):
        return jsonify({"error": "book_id and member_id are required"}), 400
    if data.get("due_date") and not valid_date(data["due_date"]):
        return jsonify({"error": "invalid due_date"}), 400

    conn = db.connect()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (data["book_id"],)).fetchone()
    if book is None:
        conn.close()
        return jsonify({"error": "book not found"}), 404
    member = conn.execute("SELECT * FROM members WHERE id = ?", (data["member_id"],)).fetchone()
    if member is None:
        conn.close()
        return jsonify({"error": "member not found"}), 404
    if book[4] == 0:
        conn.close()
        return jsonify({"error": "book is not available"}), 409

    rows = conn.execute("SELECT * FROM loans WHERE member_id = ?", (data["member_id"],)).fetchall()
    owed = 0
    open_loans = 0
    for loan in rows:
        if loan[4] == 0:
            open_loans += 1
            owed+= fines.fine_for(loan[3])
        elif loan[6] == 0:
            owed += loan[5]
    if owed > 0:
        conn.close()
        return jsonify({"error": "member has unpaid fines"}), 409
    limit = 3
    if member[3] == "staff":
        limit = 5
    if open_loans >= limit:
        conn.close()
        return jsonify({"error": "loan limit reached"}), 409

    today = date.today()
    due_date = data.get("due_date") or (today + timedelta(days=14)).isoformat()
    cur = conn.execute(
        "INSERT INTO loans (book_id, member_id, due_date, checked_out) VALUES (?, ?, ?, ?)",
        (data["book_id"], data["member_id"], due_date, today.isoformat()),
    )
    conn.execute("UPDATE books SET available = 0 WHERE id = ?", (data["book_id"],))
    conn.commit()
    loan = conn.execute("SELECT * FROM loans WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()

    send_email(member[2], "Book checked out", "You checked out "+ book[1])
    return jsonify(loan_json(loan)), 201

@bp.route("/loans/<int:loan_id>/return", methods=["POST"])
def return_book(loan_id):
    conn = db.connect()
    loan = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    if loan is None:
        conn.close()
        return jsonify({"error": "loan not found"}), 404
    if loan[4] == 1:
        conn.close()
        return jsonify({"error": "loan already returned"}), 409

    fine = fines.fine_for(loan[3])
    conn.execute("UPDATE loans SET returned = 1, fine = ? WHERE id = ?", (fine, loan_id))
    conn.execute("UPDATE books SET available = 1 WHERE id = ?", (loan[1],))
    conn.commit()
    member = conn.execute("SELECT * FROM members WHERE id = ?", (loan[2],)).fetchone()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (loan[1],)).fetchone()
    updated = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    conn.close()

    send_email(
        member[2],
        "Book returned",
        "You returned "+book[1]+ ". Fine: $"+ str(fines.money(fine)),
    )
    return jsonify(loan_json(updated))

@bp.route("/loans/<int:loan_id>/renew", methods=["POST"])
def renew_loan(loan_id):
    conn = db.connect()
    loan = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    if loan is None:
        conn.close()
        return jsonify({"error": "loan not found"}), 404
    if loan[4] == 1:
        conn.close()
        return jsonify({"error": "loan already returned"}), 409
    if date.fromisoformat(loan[3]) < date.today():
        conn.close()
        return jsonify({"error": "overdue loans cannot be renewed"}), 409
    if loan[7] >= 1:
        conn.close()
        return jsonify({"error": "loan was already renewed"}), 409

    new_due = (date.fromisoformat(loan[3]) + timedelta(days=14)).isoformat()
    conn.execute("UPDATE loans SET due_date = ?, renewals = renewals + 1 WHERE id = ?", (new_due, loan_id))
    conn.commit()
    member = conn.execute("SELECT * FROM members WHERE id = ?", (loan[2],)).fetchone()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (loan[1],)).fetchone()
    updated = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    conn.close()

    send_email(member[2],"Loan renewed","You renewed "+ book[1])
    return jsonify(loan_json(updated))

@bp.route("/loans/<int:loan_id>/pay-fine", methods=["POST"])
def pay_fine(loan_id):
    conn = db.connect()
    loan = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    if loan is None:
        conn.close()
        return jsonify({"error": "loan not found"}), 404
    if loan[4] == 0:
        conn.close()
        return jsonify({"error": "return the book before paying"}), 409
    if loan[5] <= 0 or loan[6] == 1:
        conn.close()
        return jsonify({"error": "no fine to pay"}), 409

    conn.execute("UPDATE loans SET fine_paid = 1 WHERE id = ?", (loan_id,))
    conn.commit()
    member = conn.execute("SELECT * FROM members WHERE id = ?", (loan[2],)).fetchone()
    updated = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    conn.close()

    send_email(member[2],'Fine paid',"We received $"+str(fines.money(loan[5])))
    return jsonify(loan_json(updated))