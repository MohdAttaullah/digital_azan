CREATE TABLE snooze_windows (
    id INTEGER PRIMARY KEY,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL
);
CREATE INDEX snooze_due ON snooze_windows(starts_at, ends_at);
