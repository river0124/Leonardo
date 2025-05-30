# trade_manager.py

from loguru import logger
import os
from settings import cfg
import json
from slack_notifier import post_to_slack
import time
from datetime import datetime, time as dt_time, timedelta
from websocket_manager import Websocket_Manager, websocket_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")
STOPLOSS_FILE_NAME = "stoploss.json"

ORDER_TYPE_LIMIT = "00"  # 지정가
ORDER_TYPE_MARKET = "01"  # 시장가

ATR_MULTIPLIER_STOPLOSS = 2
ATR_MULTIPLIER_TRAIL = 2

MARKET_OPEN_TIME = dt_time(8, 40)  # 장 시작 시간 (예: 정규장 시작 20분 전부터 감시 시작)
MARKET_CLOSE_TIME = dt_time(15, 31)  # 장 마감 시간 (예: 정규장 마감 1분 후까지 감시)

DEBUG = cfg.get("DEBUG", "False").lower() == "true"

class TradeManager:
    def __init__(self, api, cfg, approval_key, execution_queue, websocket_manager):
        self.api = api
        self.cfg = cfg
        self.approval_key = approval_key
        # 주문 감시 큐 (체결 대기 주문)
        self.watch_orders = []
        # 주문 처리 큐 초기화
        self.order_queue = execution_queue
        self.websocket_manager = websocket_manager

    def _read_json_file(self, file_path, default_data=None):
        """Helper function to read a JSON file."""
        if not os.path.exists(file_path):
            logger.debug(f"JSON 파일 없음: {file_path}. 기본 데이터 반환.")
            return default_data if default_data is not None else {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"⚠️ JSON decode error in {file_path}. Returning default data.")
            return default_data if default_data is not None else {}
        except IOError as e:
            logger.error(f"⚠️ IOError reading {file_path}: {e}")
            return default_data if default_data is not None else {}

    def _write_json_file(self, file_path, data):
        """Helper function to write data to a JSON file."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            logger.error(f"⚠️ IOError writing to {file_path}: {e}")
            return False

    async def place_order_with_stoploss(self, stock_code, qty, price, atr, order_type, timeout=5):

        order_type_normalized = str(order_type).strip()

        if order_type_normalized == "시장가":
            ord_dvsn = ORDER_TYPE_MARKET
            ord_unpr = "01"
        else:
            ord_dvsn = ORDER_TYPE_LIMIT
            ord_unpr = "00"

        logger.debug(f"💬 주문 딕셔너리: stock_code={stock_code}, qty={qty}, price={price}, atr={atr}, order_type={order_type}")

        try:
            await self.websocket_manager.run_websocket()
        except Exception as e:
            logger.error(f"❌ websocket_manager.run_websocket() 호출 중 예외 발생: {e}")

        if qty is None:
            logger.warning(f"⚠️ 수량(qty)이 None입니다! stock_code: {stock_code}, 요청 정보 확인 필요.")

        logger.info(f"📤 [{stock_code}] {qty}주 주문 실행 (유형: {order_type}, 가격: {price}, ATR: {atr})")

        try:
            response = self.api.do_buy(stock_code, qty, ord_unpr, ord_dvsn)
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 주문 요청 중 예외 발생: {e}")
            post_to_slack(f"❌ 주문 요청 실패: {stock_code} → {e}")
            return {"error": f"주문 요청 실패: {e}", "success": False}

        if response and hasattr(response, "_resp") and hasattr(response._resp, "text"):
            try:
                logger.debug(f"[DEBUG] 주문 응답 원문: {response._resp.text}")
            except Exception as e:
                logger.warning(f"[DEBUG] 주문 응답 원문 로깅 실패: {e}")

        if not response or not response.is_ok():
            error_msg = response.get_error_message() if response else 'API 응답 없음'
            logger.error(f"❌ [{stock_code}] 주문 실패: {error_msg}")
            post_to_slack(f"❌ 주문 실패: {stock_code} → {error_msg}")
            return {"error": f"주문 실패: {error_msg}", "success": False}

        order_body = response.get_body()
        order_output = getattr(order_body, "output", {})
        order_id = order_output.get("ODNO")

        if not order_id:
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
            "timeout": timeout
        })

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
                # 누적 체결 수량 업데이트
                order.setdefault("filled_qty", 0)
                order["filled_qty"] += qty_filled

                logger.info(f"📥 {stock_code} {qty_filled}주 체결되었습니다.")
                post_to_slack(f"📥 {stock_code} {qty_filled}주 체결되었습니다.")

                # 전체 주문 수량과 같아지면 완료
                if order["filled_qty"] >= order["qty"]:
                    logger.info(f"✅ {stock_code} 전체 {order['qty']}주 매수가 완료되었습니다.")
                    post_to_slack(f"✅ {stock_code} 전체 {order['qty']}주 매수가 완료되었습니다.")
                    self.watch_orders.remove(order)
                    if websocket_manager:
                        cmd = 8 if self.cfg.get("is_paper_trading", True) else 6
                        send_data = self.api.get_send_data(cmd=cmd)
                        send_data["approval_key"] = self.approval_key
                        await websocket_manager.send(send_data)
                        logger.info(f"📴 [{stock_code}] 체결통보 해제 요청 보냄")

                break

    async def process_execution_queue(self):
        while True:
            try:
                task = await self.order_queue.get()
                stock_code = task.get("stock_code")
                qty = task.get("qty")
                price = task.get("price")
                atr = task.get("atr")
                order_type = task.get("order_type", "시장가")
                await self.place_order_with_stoploss(stock_code, qty, price, atr, order_type)
            except Exception as e:
                logger.error(f"❌ 큐 처리 중 오류 발생: {e}")