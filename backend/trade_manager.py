import asyncio
from loguru import logger
import os
from settings import cfg
from slack_notifier import post_to_slack
import time
from websocket_manager import Websocket_Manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")

ORDER_TYPE_LIMIT = "00"  # 지정가
ORDER_TYPE_MARKET = "01"  # 시장가

DEBUG = cfg.get("DEBUG", "False").lower() == "true"

class TradeManager:
    def __init__(self, cfg, api, execution_queue=None):
        self.cfg = cfg
        self.api = api
        self.order_queue = execution_queue
        self.websocket_manager = Websocket_Manager(cfg, api)
        self.watch_orders = []

    async def place_order_with_stoploss(self, stock_code, qty, price, atr, order_type, timeout=5):
        order_type_normalized = str(order_type).strip()

        if order_type_normalized == "시장가":
            ord_dvsn = ORDER_TYPE_MARKET
            ord_unpr = "01"
        else:
            ord_dvsn = ORDER_TYPE_LIMIT
            ord_unpr = "00"

        if DEBUG:
            logger.debug(f"💬 주문 딕셔너리: stock_code={stock_code}, qty={qty}, price={price}, atr={atr}, order_type={order_type}")

        if qty is None:
            if DEBUG:
                logger.warning(f"⚠️ 수량(qty)이 None입니다! stock_code: {stock_code}")

        if DEBUG:
            logger.info(f"📤 [{stock_code}] {qty}주 주문 실행 (유형: {order_type}, 가격: {price}, ATR: {atr})")

        # WebSocket 실시간 수신 루프 시작 (체결통보 등록 포함)
        asyncio.create_task(self.websocket_manager.run_forever(auto_register_notice=True))

        try:
            await self.websocket_manager.register_execution_notice()
            if DEBUG:
                logger.info(f"📡 [{stock_code}] 체결통보 웹소켓 등록 완료")
            response = self.api.do_buy(stock_code, qty, ord_unpr, ord_dvsn)
        except Exception as e:
            if DEBUG:
                logger.error(f"❌ [{stock_code}] 주문 요청 중 예외 발생: {e}")
            post_to_slack(f"❌ 주문 요청 실패: {stock_code} → {e}")
            return {"error": f"주문 요청 실패: {e}", "success": False}

        if response and hasattr(response, "_resp") and hasattr(response._resp, "text"):
            try:
                if DEBUG:
                    logger.debug(f"[DEBUG] 주문 응답 원문: {response._resp.text}")
            except Exception as e:
                if DEBUG:
                    logger.warning(f"[DEBUG] 주문 응답 원문 로깅 실패: {e}")

        if response and response.is_ok():
            if DEBUG:
                logger.info(f"📦 [{stock_code}] 주문 API 응답 정상 수신")

        if not response or not response.is_ok():
            error_msg = response.get_error_message() if response else 'API 응답 없음'
            if not error_msg:
                try:
                    resp_text = response._resp.text if response and hasattr(response, "_resp") else None
                    if resp_text:
                        import json
                        msg1 = json.loads(resp_text).get("msg1", "")
                        error_msg = msg1 if msg1 else "알 수 없는 오류 발생"
                except Exception as e:
                    if DEBUG:
                        logger.warning(f"응답 메시지 파싱 실패: {e}")
                    error_msg = "알 수 없는 오류 발생"
            if DEBUG:
                logger.error(f"❌ [{stock_code}] 주문 실패: {error_msg}")
            post_to_slack(f"❌ 주문 실패: {stock_code} → {error_msg}")
            return {"error": f"주문 실패: {error_msg}", "success": False}

        order_body = response.get_body()
        order_output = getattr(order_body, "output", {})
        order_id = order_output.get("ODNO")

        if not order_id:
            if DEBUG:
                logger.error(f"❌ [{stock_code}] 주문 응답 본문 오류 또는 주문번호(ODNO) 없음: {order_output}")
            post_to_slack(f"❌ 주문 응답 본문 오류: {stock_code}")
            return {"error": "주문 응답 본문 오류", "success": False}

        self.watch_orders.append({
            "stock_code": stock_code,
            "order_id": order_id,
            "qty": qty,
            "atr": atr,
            "price": price,
            "order_time": time.time(),
            "timeout": timeout,
            "filled_qty": 0,
        })
        if DEBUG:
            logger.debug(f"📊 현재 감시 중인 주문 수: {len(self.watch_orders)}")

        if DEBUG:
            logger.info(f"✅ [{stock_code}] 주문 성공 및 감시 등록 완료. 주문번호: {order_id}")

        return {
            "order_id": order_id,
            "stock_code": stock_code,
            "initial_qty": qty,
            "success": True,
            "message": f"[{stock_code}] 주문번호 {order_id} 감시 등록 완료."
        }

    async def handle_execution(self, execution_msg):
        order_no = execution_msg["body"]["ODER_NO"]
        stock_code = execution_msg["body"]["STCK_SHRN_ISCD"]
        qty_filled = int(execution_msg["body"]["CNTG_QTY"])

        for order in self.watch_orders:
            if order["order_id"] == order_no and order["stock_code"] == stock_code:
                order["filled_qty"] += qty_filled

                if DEBUG:
                    logger.info(f"📥 {stock_code} {qty_filled}주 체결되었습니다.")
                post_to_slack(f"📥 {stock_code} {qty_filled}주 체결되었습니다.")

                if order["filled_qty"] >= order["qty"]:
                    if DEBUG:
                        logger.info(f"✅ {stock_code} 전체 {order['qty']}주 매수가 완료되었습니다.")
                    post_to_slack(f"✅ {stock_code} 전체 {order['qty']}주 매수가 완료되었습니다.")
                    await self.websocket_manager.unregister_execution_notice(stock_code)
                    self.watch_orders.remove(order)
                break
        else:
            if DEBUG:
                logger.warning(f"📛 체결 메시지 무시됨. 일치하는 주문 없음: order_no={order_no}, stock_code={stock_code}")

    async def process_execution_queue(self):
        while True:
            if DEBUG:
                logger.debug("🔁 [TradeManager] 실행 큐 루프 진입")
            try:
                task = await self.order_queue.get()

                if task is None:
                    if DEBUG:
                        logger.warning("큐에서 None 작업 수신, 무시함")
                    continue

                if not isinstance(task, dict):
                    if DEBUG:
                        logger.warning(f"큐에서 dict가 아닌 항목 수신: {task}, 무시함")
                    continue

                stock_code = task.get("stock_code")
                qty = task.get("qty")
                price = task.get("price")
                atr = task.get("atr")
                order_type = task.get("order_type", "시장가")

                if DEBUG:
                    logger.debug(f"큐 작업 처리 시작: {task}")

                await self.place_order_with_stoploss(stock_code, qty, price, atr, order_type)

            except Exception as e:
                if DEBUG:
                    logger.error(f"❌ 큐 처리 중 오류 발생: {e}", exc_info=True)


    async def handle_ws_message(self, message: dict):
        """
        WebsocketManager가 실시간 체결 메시지를 전달할 때 호출됨.
        체결 메시지를 내부 handle_execution()으로 위임 처리.
        """
        try:
            if message.get("body") and "ODER_NO" in message["body"]:
                await self.handle_execution(message)
        except Exception as e:
            if DEBUG:
                logger.error(f"❌ 실시간 체결 메시지 처리 중 오류 발생: {e}")