import subprocess
from pathlib import Path
import sys,os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from slack_notifier import post_to_slack

# 각 스크립트 경로 정의
scripts = [
    "/Users/hyungseoklee/Documents/Leonardo/backend/auto_updaters/update_stock_names.py",
    "/Users/hyungseoklee/Documents/Leonardo/backend/auto_updaters/fill_sector_from_fnguide.py",
    "/Users/hyungseoklee/Documents/Leonardo/backend/auto_updaters/sector_utils.py",
    "/Users/hyungseoklee/Documents/Leonardo/backend/auto_updaters/find_52week_high_candidates.py",
]

PYTHON_EXECUTABLE = "/opt/anaconda3/envs/py310env/bin/python"

def run_scripts_sequentially():
    for script in scripts:
        print(f"⏳ 실행 중: {Path(script).name}")
        result = subprocess.run([PYTHON_EXECUTABLE, script])
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
