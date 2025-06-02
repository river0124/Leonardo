import asyncio

async def simulate_websocket(execution_queue):
    print("🌐 WebSocket 연결됨 (시뮬레이션)")
    await asyncio.sleep(1)  # 실제 체결 지연을 흉내냄
    sample_execution = {"stock_code": "005930", "price": 72000}
    await execution_queue.put(sample_execution)
    print("📤 체결 정보 전송 완료 - 웹소켓")