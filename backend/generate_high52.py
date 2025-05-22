from find_52week_high_candidates import find_52week_high_candidates
import json
from slack_notifier import post_to_slack

try:
    df = find_52week_high_candidates()
    with open("/Users/hyungseoklee/Documents/Leonardo/backend/cache/high52.json", "w", encoding="utf-8") as f:
        json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)

    post_to_slack("✅ 52주 신고가 리스트 업데이트 완료", config_path="/Users/hyungseoklee/Documents/Leonardo/backend/config.yaml")

except Exception as e:
    post_to_slack(f"❌ 52주 신고가 실패: {e}", config_path="/Users/hyungseoklee/Documents/Leonardo/backend/config.yaml")
    raise