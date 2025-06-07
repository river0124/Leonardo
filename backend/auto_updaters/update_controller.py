import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from slack_notifier import post_to_slack  # ✅ 슬랙 전송 모듈

from dotenv import load_dotenv
import subprocess
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '.env'))  # 두 폴더 위로 변경
load_dotenv(dotenv_path=ENV_PATH, override=True)
PYTHON_EXECUTABLE = os.getenv("PYTHON_EXECUTABLE") or sys.executable
CACHE_DIR = os.getenv("CACHE_DIR", os.path.join(BASE_DIR, "cache"))

scripts = [
    os.path.join(BASE_DIR, "update_stock_names.py"),
    os.path.join(BASE_DIR, "fill_sector_from_fnguide.py"),
    os.path.join(BASE_DIR, "sector_utils.py"),
    os.path.join(BASE_DIR, "find_52week_high_candidates.py"),
]

def run_scripts_sequentially():
    for script in scripts:
        print(f"⏳ 실행 중: {Path(script).name}")
        result = subprocess.run([sys.executable, script])
        if result.returncode != 0:
            print(f"❌ 오류 발생: {Path(script).name} 실행 중단")
            break
        else:
            print(f"✅ 완료: {Path(script).name}")

if __name__ == "__main__":
    print("📅 매일 자동 업데이트 시작")
    post_to_slack("📅 매일 자동 업데이트 시작")
    run_scripts_sequentially()
    print("🎉 모든 작업 완료")
    post_to_slack("🎉 모든 작업 완료")
