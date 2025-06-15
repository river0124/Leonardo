import json
from pathlib import Path
import os

BASE_DIR = os.getenv('BASE_DIR', os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.getenv('CACHE_DIR', os.path.join(BASE_DIR, 'cache'))
SETTINGS_FILE = os.getenv('SETTINGS_FILE', os.path.join(CACHE_DIR, 'settings.json'))
SETTINGS_PATH = Path(SETTINGS_FILE)

def set_is_paper_trading(value: bool):
    if not SETTINGS_PATH.exists():
        raise FileNotFoundError(f"Settings file not found at {SETTINGS_PATH}")

    with SETTINGS_PATH.open("r", encoding="utf-8") as f:
        settings = json.load(f)

    settings["is_paper_trading"] = value

    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    flg = True
    set_is_paper_trading(flg)