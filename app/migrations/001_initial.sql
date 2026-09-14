CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE occurrences (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    prayer TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    effective_time TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    timing_source TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL CHECK(status IN ('PENDING','PLAYING','PLAYED','DISABLED',
        'SKIPPED','SUPPRESSED','STOPPED_BY_USER','MISSED_DOWNTIME','FAILED')),
    audio_file TEXT,
    started_at TEXT,
    completed_at TEXT,
    suppression_reason TEXT,
    failure_reason TEXT,
    UNIQUE(date, prayer)
);
CREATE INDEX occurrences_due ON occurrences(status, scheduled_at);
CREATE TABLE rotations (collection TEXT PRIMARY KEY, last_file TEXT NOT NULL);
CREATE TABLE events (
    id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL,
    occurrence_id INTEGER, detail TEXT NOT NULL
);
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX one_active_profile ON profiles(active) WHERE active = 1;
CREATE TABLE overrides (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    date TEXT NOT NULL, fajr TEXT, maghrib TEXT, notes TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(profile_id, date)
);
CREATE TABLE legacy_triggers (
    date TEXT NOT NULL, prayer TEXT NOT NULL, PRIMARY KEY(date, prayer)
);
