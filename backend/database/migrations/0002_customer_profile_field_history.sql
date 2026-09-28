-- Audit log table: holds every prior value of a customer_profiles field,
-- written by the versioned-upsert logic in db_manager before it overwrites
-- the current value. Rows are never updated or deleted.
CREATE TABLE IF NOT EXISTS customer_profile_field_history (
    id BIGSERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer_profiles(customer_id),
    field_name TEXT NOT NULL,
    value JSONB,
    source TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_profile_field_history_lookup
    ON customer_profile_field_history (customer_id, field_name, recorded_at);
