from flask import Blueprint, jsonify, request
import db

bp = Blueprint('books', __name__)

def valid_isbn(value):
    digits = str(value).replace("-", "")
    return digits.isdigit() and len(digits) in (10, 13)

@bp.route("/books", methods =["GET"])
def list_books():
    conn = db.connect()
    if request.args.get("available") == "true":
        rows = conn.execute("SELECT * FROM books WHERE available = 1").fetchall()
    else:
        rows = conn.execute("SELECT * FROM books").fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({"id": r[0], "title": r[1], "author": r[2], "isbn": r[3], "available": bool(r[4])})
    return jsonify(result)

@bp.route("/books/<int:book_id>", methods=["GET"])
def get_book(book_id):
    conn = db.connect()
    r = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.close()
    if r is None:
        return jsonify({"error": "book not found"}), 404
    return jsonify({"id": r[0], "title": r[1], "author": r[2], "isbn": r[3], "available": bool(r[4])})

@bp.route("/books", methods=["POST"])
def create_book():
    data = request.get_json(silent=True) or {}
    if not data.get("title") or not data.get("author"):
        return jsonify({"error": "title and author are required"}), 400
    if not valid_isbn(data.get("isbn")):
        return jsonify({"error": "invalid isbn"}), 400
    conn = db.connect()
    cur = conn.execute(
        "INSERT INTO books (title, author, isbn, available) VALUES (?, ?, ?, 1)",
        (data["title"], data["author"], data["isbn"]),
    )
    conn.commit()
    r = conn.execute("SELECT * FROM books WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify({"id": r[0], "title": r[1], "author": r[2], "isbn": r[3], "available": bool(r[4])}), 201

@bp.route("/books/<int:book_id>", methods=["DELETE"])
def delete_book(book_id):
    conn = db.connect()
    r = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if r is None:
        conn.close()
        return jsonify({"error": "book not found"}), 404
    if r[4] == 0:
        conn.close()
        return jsonify({"error": "book is on loan"}), 409
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()
    return "", 204