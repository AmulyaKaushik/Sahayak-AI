CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id TEXT PRIMARY KEY,
    monthly_income NUMERIC,
    age INTEGER,
    dependents INTEGER,
    employment_type TEXT,
    existing_products TEXT[] NOT NULL DEFAULT '{}',
    language_preference TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
