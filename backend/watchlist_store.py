# watchlist_store.py
import json
import os

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "cache", "watchlist.json")

def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)

def add_code_to_watchlist(code):
    watchlist = load_watchlist()
    if code not in watchlist:
        watchlist.append(code)
        save_watchlist(watchlist)

def remove_code_from_watchlist(code):
    watchlist = load_watchlist()
    if code in watchlist:
        watchlist.remove(code)
        save_watchlist(watchlist)