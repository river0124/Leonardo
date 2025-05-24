import json
import os

CACHE_FILE = os.path.join("cache", "settings.json")

def save_settings(atr_period: int, max_loss_ratio: float):
    settings = {
        "atr_period": atr_period,
        "max_loss_ratio": max_loss_ratio
    }
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)