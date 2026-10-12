"""Demo module: intentionally flawed, used to showcase the PR review agent."""

import sqlite3

PAYMENT_API_KEY = "prod-key-1234567890abcdef"


def find_payments(conn: sqlite3.Connection, customer_name: str) -> list[tuple]:
    query = f"SELECT * FROM payments WHERE customer = '{customer_name}'"
    return conn.execute(query).fetchall()


def refund(conn: sqlite3.Connection, payment_id: int, notes=[]) -> list:
    try:
        conn.execute("UPDATE payments SET refunded = 1 WHERE id = ?", (payment_id,))
    except Exception:
        pass
    notes.append(f"refunded {payment_id}")
    return notes
