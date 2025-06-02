from flask import Flask, jsonify
import threading
import asyncio

from websocket_simulator import simulate_websocket
from trade_manager import trade_manager_loop

app = Flask(__name__)

# 비동기 큐 생성
execution_queue = asyncio.Queue()

# 별도 이벤트 루프 생성 및 설정
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# TradeManager 비동기 루프 시작
loop.create_task(trade_manager_loop(execution_queue))

@app.route('/trigger', methods=['POST'])
def trigger_websocket():
    asyncio.run_coroutine_threadsafe(simulate_websocket(execution_queue), loop)
    return jsonify({"status": "WebSocket 트리거 완료"})

if __name__ == '__main__':
    # 이벤트 루프 백그라운드에서 실행
    threading.Thread(target=loop.run_forever, daemon=True).start()
    # Flask는 메인 스레드에서 실행
    app.run(debug=True)