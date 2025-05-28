import asyncio
import json
from websocket_manager import WebSocketManager
from utils import KoreaInvestAPI, KoreaInvestEnv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(BASE_DIR, "cache", "settings.json")

with open(settings_path, "r") as f:
    cfg = json.load(f)

async def main():

    # API 및 웹소켓 매니저 초기화
    base_headers = {
        "content_Type": "application/json",
        "Accept": "text/plain",
        "charset": "UTF-8",
        "User_Agent": "",
        "appsecret": cfg["api_secret_key"],
        "tr_id": "",
        "custtype": "P"
    }
    api = KoreaInvestAPI(cfg, base_headers)
    manager = WebSocketManager(api, cfg)

    print("🔌 웹소켓 연결 중...")
    await manager.connect("ws://ops.koreainvestment.com:31000")  # 모의투자 주소
    print("✅ 연결 완료!")

    stock_code = "005930"  # 삼성전자
    print(f"📡 삼성전자({stock_code}) 체결통보 구독 시작")
    await manager.subscribe_stock(stock_code)

    await asyncio.sleep(60)  # 1분 대기

    print(f"❌ 삼성전자({stock_code}) 체결통보 해지")
    await manager.unsubscribe_stock(stock_code)

    print("🔒 연결 종료")
    await manager.close()

if __name__ == "__main__":
    asyncio.run(main())