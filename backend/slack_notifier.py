import yaml
CONFIG_PATH = "/Users/hyungseoklee/Documents/Leonardo/backend/config.yaml"


# 설정 파일에서 Webhook URL 로드
def load_slack_webhook_url(config_path=CONFIG_PATH):
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            return config["slack"]["webhook_url"]
    except Exception as e:
        print(f"⚠️ config.yaml 로드 실패: {e}")
        return None

def post_to_slack(text: str, config_path=CONFIG_PATH):
    webhook_url = load_slack_webhook_url(config_path)
    if not webhook_url:
        print("❌ Webhook URL이 설정되지 않았습니다.")
        return
    try:
        import requests
        response = requests.post(
            webhook_url,
            json={"text": text},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code != 200:
            print(f"Slack 전송 실패: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Slack 전송 중 오류: {e}")