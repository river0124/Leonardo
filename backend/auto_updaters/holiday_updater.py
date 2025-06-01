import requests
import os
import csv
import time
from urllib.parse import urlencode
from datetime import datetime
from slack_notifier import post_to_slack  # ✅ 슬랙 모듈 추가

class HolidayAPI:
    def __init__(self, service_key):
        self.service_key = service_key
        self.base_url = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"

    def get_holidays(self, year, month):
        params = {
            'ServiceKey': self.service_key,
            'solYear': year,
            'solMonth': f"{month:02d}",
            '_type': 'json',
            'numOfRows': 100,
        }
        url = f"{self.base_url}?{urlencode(params)}"
        print(f"🔵 요청 URL: {url}")

        response = requests.get(url)

        if response.status_code == 200:
            try:
                data = response.json()
                print(f"🟢 JSON 응답 성공")
            except Exception as e:
                print(f"🔴 JSON 파싱 실패: {e}")
                return []
        else:
            print(f"🔴 HTTP 오류: {response.status_code}")
            return []

        if data.get('response', {}).get('header', {}).get('resultCode') != '00':
            print(f"🔴 API 오류: {data.get('response', {}).get('header', {}).get('resultMsg')}")
            return []

        items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        if not isinstance(items, list):
            items = [items]

        holidays = []
        for item in items:
            locdate = str(item.get('locdate'))
            dateName = item.get('dateName')
            holidays.append((locdate, dateName))

        return holidays


if __name__ == "__main__":
    try:
        SERVICE_KEY = os.getenv(
            'niEfT%2BlkaY3%2BgMAppB96j%2FrZpvCKcJWgDrrp9D2Xtd9n0X%2BSE9czZ0uqFWtwYI0jZuq1G0smE%2FUh7xh9HAqo8Q%3D%3D',
            'niEfT+lkaY3+gMAppB96j/rZpvCKcJWgDrrp9D2Xtd9n0X+SE9czZ0uqFWtwYI0jZuq1G0smE/Uh7xh9HAqo8Q=='
        )

        api = HolidayAPI(SERVICE_KEY)

        now = datetime.now()
        start_year = now.year - 5
        end_year = now.year + 1

        all_holidays = []

        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                try:
                    holidays = api.get_holidays(year, month)
                    all_holidays.extend(holidays)
                    time.sleep(0.2)
                except Exception as e:
                    print(f"⚠️ {year}년 {month}월 실패: {e}")

        print(f"✅ 총 {len(all_holidays)}건 공휴일 수집 완료")

        output_file = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/holidays.csv"

        with open(output_file, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['날짜', '휴일명'])
            writer.writerows(all_holidays)

        print(f"📄 CSV 파일 저장 완료: {output_file}")

        # ✅ 슬랙 알림 전송
        post_to_slack(f"✅ 공휴일 정보 {len(all_holidays)}건 수집 완료 및 저장됨")

    except Exception as e:
        post_to_slack(f"❌ 공휴일 수집 실패: {e}")
        raise