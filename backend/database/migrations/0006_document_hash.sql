-- Lets the folder sync recognise a PDF it has already ingested (by content),
-- so re-running the sync never duplicates a document.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents (content_hash);
