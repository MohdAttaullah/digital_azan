import json
from datetime import date
from pathlib import Path
from typing import Dict


STATE_DIR = Path("state")
STATE_FILE = STATE_DIR / "scheduler_state.json"


def _default_state():
    return {
        "date": date.today().isoformat(),
        "triggered": {}
    }


def load_state() -> Dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not STATE_FILE.exists():
        return _default_state()

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()

    # Reset daily
    if state.get("date") != date.today().isoformat():
        return _default_state()

    return state


def save_state(state: Dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
