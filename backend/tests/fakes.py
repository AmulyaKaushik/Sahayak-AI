"""In-memory stand-ins so the auth/session/profile flow can be tested
without Postgres or Redis."""

import uuid

from security import repository as auth_repository


class FakeRedis:
    def __init__(self):
        self.data: dict = {}

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def expire(self, key, seconds):
        return True

    def set(self, key, value, ex=None):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        self.data.pop(key, None)


def install_fake_auth_backend(monkeypatch) -> FakeRedis:
    import security.redis_client as redis_client

    fake = FakeRedis()
    monkeypatch.setattr(redis_client, "_client", fake)

    customers: dict[str, auth_repository.Customer] = {}

    def create_customer(login_id, password_hash):
        if any(c.login_id == login_id for c in customers.values()):
            raise auth_repository.LoginIdTaken(login_id)
        customer = auth_repository.Customer(str(uuid.uuid4()), login_id, password_hash, False)
        customers[customer.customer_id] = customer
        return customer

    monkeypatch.setattr(auth_repository, "create_customer", create_customer)
    monkeypatch.setattr(
        auth_repository, "get_by_login_id",
        lambda login_id: next((c for c in customers.values() if c.login_id == login_id), None),
    )
    monkeypatch.setattr(auth_repository, "get_by_id", customers.get)
    monkeypatch.setattr(auth_repository, "touch_last_login", lambda customer_id: None)
    monkeypatch.setattr(
        auth_repository, "is_profile_completed",
        lambda cid: customers[cid].profile_completed if cid in customers else False,
    )

    def mark_profile_completed(cid):
        customers[cid].profile_completed = True

    monkeypatch.setattr(auth_repository, "mark_profile_completed", mark_profile_completed)
    return fake
