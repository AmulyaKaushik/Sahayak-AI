-- Rules config table. Rows are append-only per version (never mutated in
-- place), so this table doubles as its own audit trail.
CREATE TABLE IF NOT EXISTS eligibility_rules (
    scheme_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    conditions JSONB NOT NULL,
    source_document TEXT,
    approved_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (scheme_id, version)
);

CREATE INDEX IF NOT EXISTS idx_eligibility_rules_active
    ON eligibility_rules (scheme_id)
    WHERE is_active;
