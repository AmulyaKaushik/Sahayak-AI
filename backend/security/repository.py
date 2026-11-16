"""customers (auth) table access. Identity only -- the profile data itself
stays in customer_profiles, owned by db_manager."""

import uuid
from dataclasses import dataclass

import psycopg

from database.db import get_connection


@dataclass
class Customer:
    customer_id: str
    login_id: str
    password_hash: str
    profile_completed: bool


class LoginIdTaken(Exception):
    pass


def _row_to_customer(row) -> Customer | None:
    if row is None:
        return None
    return Customer(
        customer_id=row[0], login_id=row[1], password_hash=row[2], profile_completed=row[3]
    )


def create_customer(login_id: str, password_hash: str) -> Customer:
    customer_id = str(uuid.uuid4())
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO customers (customer_id, login_id, password_hash) VALUES (%s, %s, %s)",
                (customer_id, login_id, password_hash),
            )
    except psycopg.errors.UniqueViolation:
        raise LoginIdTaken(login_id)
    return Customer(customer_id, login_id, password_hash, False)


def get_by_login_id(login_id: str) -> Customer | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT customer_id, login_id, password_hash, profile_completed "
            "FROM customers WHERE login_id = %s",
            (login_id,),
        ).fetchone()
    return _row_to_customer(row)


def get_by_id(customer_id: str) -> Customer | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT customer_id, login_id, password_hash, profile_completed "
            "FROM customers WHERE customer_id = %s",
            (customer_id,),
        ).fetchone()
    return _row_to_customer(row)


def touch_last_login(customer_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE customers SET last_login_at = now() WHERE customer_id = %s", (customer_id,)
        )


def is_profile_completed(customer_id: str) -> bool:
    customer = get_by_id(customer_id)
    return customer.profile_completed if customer else False


def mark_profile_completed(customer_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE customers SET profile_completed = true WHERE customer_id = %s", (customer_id,)
        )
