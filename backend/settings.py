import json
from cryptography.fernet import Fernet
from loguru import logger
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '.env'))  # 두 폴더 위로 변경
load_dotenv(dotenv_path=ENV_PATH, override=True)

# 환경변수에서 경로 읽기, 없으면 기본값으로 로컬 경로 지정
CACHE_DIR = os.getenv('CACHE_DIR')
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")
FERNET_KEY_FILE = os.path.join(CACHE_DIR, "key.secret")

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
    settings = {}

    # 1) settings.json 전체 로드
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                file_settings = json.load(f)
            # papertoken, realtoken만 복호화 시도
            for key in ["papertoken", "realtoken"]:
                if key in file_settings and isinstance(file_settings[key], str):
                    try:
                        file_settings[key] = fernet.decrypt(file_settings[key].encode()).decode()
                    except Exception:
                        pass
            settings.update(file_settings)

        except json.JSONDecodeError:
            if DEBUG:
                logger.info(f"⚠️ JSON 디코딩 실패: {SETTINGS_FILE}")
    else:
        if DEBUG:
            logger.info(f"📁 설정 파일이 존재하지 않음: {SETTINGS_FILE}")

    # 2) .env에서 키값 로드 및 덮어쓰기 (None인 값 제외)
    env_api_keys = {
        "api_key": os.getenv("api_key"),
        "api_secret_key": os.getenv("api_secret_key"),
        "paper_api_key": os.getenv("paper_api_key"),
        "paper_api_secret_key": os.getenv("paper_api_secret_key"),
        "stock_account_number": os.getenv("stock_account_number"),
        "paper_stock_account_number": os.getenv("paper_stock_account_number"),
        "htsid": os.getenv("htsid"),
        "custtype": os.getenv("custtype"),
        "user_agent": os.getenv("user_agent"),
        "url": os.getenv("url"),
        "websocket_url": os.getenv("websocket_url"),
        "paper_url": os.getenv("paper_url"),
        "paper_websocket_url": os.getenv("paper_websocket_url"),
        "slack_webhook_url": os.getenv("slack_webhook_url"),
        "CACHE_DIR": os.getenv("CACHE_DIR"),
        "PYTHON_EXECUTABLE": os.getenv("PYTHON_EXECUTABLE")
    }
    for k, v in env_api_keys.items():
        if v is not None:
            settings[k] = v

    return settings

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