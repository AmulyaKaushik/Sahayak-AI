-- Auth identity table. Separate from customer_profiles (which stays the
-- profile store); customer_id is the same TEXT key and is the JWT "sub".
CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    login_id      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    profile_completed BOOLEAN NOT NULL DEFAULT false
);
