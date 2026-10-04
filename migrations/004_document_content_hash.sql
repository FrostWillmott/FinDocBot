-- SHA-256 of the uploaded bytes; the unique index makes a re-upload of the
-- same PDF resolve to the existing document instead of a second copy.
-- Rows from before this migration keep NULL (their bytes were not stored),
-- and NULLs never collide, so existing duplicates stay until deleted.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_content_hash
    ON documents(content_hash);
