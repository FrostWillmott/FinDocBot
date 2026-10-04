-- Chat sessions issued by the server. /ask accepts only ids listed here, so
-- a client cannot pick, guess or reuse another client's session id.
-- No FK from chat_turns: turns stored before this migration carry
-- client-chosen ids with no row here; they simply become unreachable.
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
