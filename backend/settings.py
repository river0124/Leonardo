import json
from cryptography.fernet import Fernet
from loguru import logger
import os
from dotenv import load_dotenv

load_dotenv()

# 환경 변수 APP_ENV에 따라 환경 분리(local, server)
APP_ENV = os.getenv("APP_ENV", "local").lower()

# 기본 경로 분리
if APP_ENV == "server":
    BASE_DIR = "/home/ubuntu/backend"
    DEBUG = False
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DEBUG = True

CACHE_DIR = os.path.join(BASE_DIR, "cache")
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")
FERNET_KEY_FILE = os.path.join(CACHE_DIR, "key.secret")

if DEBUG:
    logger.info(f"BASE_DIR = {BASE_DIR}")
    logger.info(f"CACHE_DIR = {CACHE_DIR}")
    logger.info(f"SETTINGS_FILE = {SETTINGS_FILE}")
    logger.info(f"파일 존재 여부 = {os.path.exists(SETTINGS_FILE)}")
    logger.info(f"현재 작업 디렉토리: {os.getcwd()}")

# --- 암호화 키 준비 ---
if os.path.exists(FERNET_KEY_FILE):
    with open(FERNET_KEY_FILE, "rb") as f:
        FERNET_KEY = f.read()
else:
    FERNET_KEY = Fernet.generate_key()
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(FERNET_KEY_FILE, "wb") as f:
        f.write(FERNET_KEY)

fernet = Fernet(FERNET_KEY)

# --- 설정 로딩 ---
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            for key in ["api_key", "api_secret_key", "paper_api_key", "paper_api_secret_key", "papertoken", "realtoken"]:
                if key in settings and isinstance(settings[key], str):
                    try:
                        settings[key] = fernet.decrypt(settings[key].encode()).decode()
                    except Exception:
                        pass
            if DEBUG:
                logger.info(f"📥 설정 불러오기 완료: {settings}")  # 필요 시 주석 해제
            return settings
        except json.JSONDecodeError:
            if DEBUG:
                logger.info(f"⚠️ JSON 디코딩 실패: {SETTINGS_FILE}")
            return {}
    else:
        if DEBUG:
            logger.info(f"📁 설정 파일이 존재하지 않음: {SETTINGS_FILE}")
        return {}

# --- 설정 저장 ---
def save_settings(settings: dict):
    current = load_settings()
    if DEBUG:
        logger.info(f"📂 기존 settings 내용: {current}")

    for key in ["api_key", "access_token"]:
        if key in settings and isinstance(settings[key], str):
            settings[key] = fernet.encrypt(settings[key].encode()).decode()

    merged = {**current, **settings}
    if DEBUG:
        logger.info(f"📝 저장할 settings 내용: {merged}")

    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    if DEBUG:
        logger.info(f"✅ settings 저장 완료: {SETTINGS_FILE}")

# --- 외부 노출 변수 ---
cfg = load_settings()