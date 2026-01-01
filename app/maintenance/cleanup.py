from pathlib import Path
from datetime import datetime, timedelta
import json


def cleanup_old_event_files(
    events_dir: Path,
    keep_days: int = 7,
) -> int:
    """
    Deletes JSON event files older than `keep_days`.
    Returns number of files deleted.
    """
    if not events_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=keep_days)
    deleted = 0

    for file in events_dir.glob("*.json"):
        try:
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if mtime < cutoff:
                file.unlink()
                deleted += 1
        except Exception as e:
            print(f"[CLEANUP] Failed to delete {file.name}: {e}")

    if deleted:
        print(f"[CLEANUP] Deleted {deleted} old event files")

    return deleted
