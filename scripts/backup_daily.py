from datetime import datetime, timezone

from app.config import load_config
from app.storage import Store

if __name__ == "__main__":
    cfg = load_config()
    name = datetime.now(timezone.utc).strftime("azan-%Y%m%dT%H%M%SZ.sqlite3")
    destination = cfg.data_dir / "backups" / name
    Store(cfg.database, migrate=False).backup(destination)
    print(f"Verified backup: {destination}")
