# subscribe_execution_notice.py

import asyncio
from websocket_manager import Websocket_Manager, websocket_manager
from utils_backup import KoreaInvestEnv
from settings import cfg

class SimpleListener:
    async def handle_ws_message(self, message):
        print(f"🔔 체결 통보 수신: {message}")

async def main():
    env = KoreaInvestEnv(cfg)
    approval_key = env.get_websocket_approval_key()

    # Websocket_Manager 인스턴스 생성
    global websocket_manager
    websocket_manager = Websocket_Manager(cfg, approval_key)

    # 체결 통보 핸들링을 위한 리스너 설정
    listener = SimpleListener()
    websocket_manager.set_listener(listener)

    # 웹소켓 실행
    await websocket_manager.run_websocket()

if __name__ == "__main__":
    asyncio.run(main())