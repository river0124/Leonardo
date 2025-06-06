from dotenv import load_dotenv
import os
import requests

load_dotenv()  # .env 파일에서 환경변수 로드

# .env에서 슬랙 웹훅 URL을 바로 읽도록 변경
slack_webhook_url = os.getenv("slack_webhook_url")

def post_to_slack(text: str):
    if not slack_webhook_url:
        print("❌ Webhook URL이 설정되지 않았습니다.")
        return
    try:
        response = requests.post(
            slack_webhook_url,
            json={"text": text},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code != 200:
            print(f"Slack 전송 실패: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Slack 전송 중 오류: {e}")