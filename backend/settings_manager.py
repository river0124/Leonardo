import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "cache", "settings.json")

def save_settings(settings_dict: dict):
    # 기존 설정 불러오기 (없으면 빈 dict)
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            print("📂 기존 settings 내용:", settings)
    else:
        print(f"📁 설정 파일이 존재하지 않아 새로 생성합니다: {CACHE_FILE}")
        settings = {}

    # 값 업데이트
    settings.update(settings_dict)
    print("📝 저장할 settings 내용:", settings)

    # 저장
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    print(f"✅ settings 저장 완료: {CACHE_FILE}")

def load_settings():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            return settings
    else:
        return {}