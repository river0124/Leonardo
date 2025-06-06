import asyncio
from loguru import logger
import os
import json
import dotenv

from settings import cfg
from slack_notifier import post_to_slack
import time
from hoga_scale import adjust_price_to_hoga
from websocket_manager import Websocket_Manager

dotenv.load_dotenv()
CACHE_DIR = os.getenv('CACHE_DIR')

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
        self.stoploss_cache = set()

    async def place_order_with_stoploss(self, stock_code, qty, price, atr, order_type):
        """
        🛒 스톱로스를 포함한 매수 주문을 실행하고 체결 감시 등록까지 수행하는 함수

        매개변수:
        - stock_code: 종목 코드 (문자열)
        - qty: 주문 수량 (정수)
        - price: 지정가 주문 시 사용되는 가격 (정수 또는 문자열)
        - atr: ATR 값, 스톱로스 계산에 사용됨 (정수)
        - order_type: 주문 유형 (예: "시장가", "지정가", "00", "01")
        - timeout: 주문 후 체결 감시를 유지할 시간 (초 단위, 기본값 5초)

        기능:
        - 주문 유형을 판단하여 시장가/지정가 주문 구성
        - 이미 체결통보 등록된 종목은 중복 등록하지 않음
        - 주문 API를 호출하고 성공 여부를 확인
        - 주문번호가 존재하면 내부 감시 리스트(self.watch_orders)에 등록
        - 에러 발생 시 슬랙 알림 전송
        """

        order_type_normalized = str(order_type).strip()

        if DEBUG: logger.debug(f"[DEBUG] 주문 유형 원본: {order_type} | 정규화 후: {order_type_normalized}")

        if order_type_normalized in ["01", "시장가"]:
            ord_dvsn = ORDER_TYPE_MARKET  # 시장가
            ord_unpr = "0"
        elif order_type_normalized in ["00", "지정가"]:
            ord_dvsn = ORDER_TYPE_LIMIT  # 지정가
            ord_unpr = str(price)
        else:
            logger.error(f"❌ 알 수 없는 order_type: {order_type_normalized}")
            return {"error": f"알 수 없는 주문 유형: {order_type_normalized}", "success": False}

        if DEBUG: logger.debug(f"[DEBUG] 결정된 주문 구분 코드: ord_dvsn={ord_dvsn}, ord_unpr={ord_unpr}")

        if DEBUG: logger.debug(f"💬 주문 딕셔너리: stock_code={stock_code}, qty={qty}, price={price}, atr={atr}, order_type={order_type}")

        if qty is None:
            if DEBUG: logger.warning(f"⚠️ 수량(qty)이 None입니다! stock_code: {stock_code}")

        if DEBUG: logger.info(f"📤 [{stock_code}] {qty}주 주문 실행 (유형: {order_type}, 가격: {price}, ATR: {atr})")

        try:
            if stock_code in self.websocket_manager.execution_notices:
                if DEBUG: logger.debug(f"🔁 [{stock_code}] 이미 체결통보 등록됨. 중복 등록 생략")
            else:
                if DEBUG: logger.debug(f"[WebSocketManager] 새로운 종목 등록 시작: {stock_code}")
                await self.websocket_manager.register_execution_notice()
                if DEBUG: logger.debug(f"📡 [{stock_code}] 체결통보 웹소켓 등록 완료")
            # Listener 등록
            self.websocket_manager.listener = self

            if DEBUG: logger.debug(f"[DEBUG] 주문 request payload: {stock_code, qty, ord_unpr, ord_dvsn}")
            response = self.api.do_buy(stock_code, qty, ord_unpr, ord_dvsn)
            if DEBUG: logger.debug(f"[DEBUG] 주문 API 응답 원문: {response}")

        except Exception as e:
            if DEBUG: logger.error(f"❌ [{stock_code}] 주문 요청 중 예외 발생: {e}")
            post_to_slack(f"❌ 주문 요청 실패: {stock_code} → {e}")
            return {"error": f"주문 요청 실패: {e}", "success": False}

        if response and hasattr(response, "_resp") and hasattr(response._resp, "text"):
            try:
                if DEBUG: logger.debug(f"[DEBUG] 주문 응답 원문: {response._resp.text}")
            except Exception as e:
                if DEBUG: logger.warning(f"[DEBUG] 주문 응답 원문 로깅 실패: {e}")

        if response and response.is_ok():
            if DEBUG: logger.info(f"📦 [{stock_code}] 주문 API 응답 정상 수신")

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
                    if DEBUG: logger.warning(f"응답 메시지 파싱 실패: {e}")
                    error_msg = "알 수 없는 오류 발생"
            if DEBUG: logger.error(f"❌ [{stock_code}] 주문 실패: {error_msg}")
            post_to_slack(f"❌ 주문 실패: {stock_code} → {error_msg}")
            return {"error": f"주문 실패: {error_msg}", "success": False}

        order_body = response.get_body()
        order_output = getattr(order_body, "output", {})
        order_id = order_output.get("ODNO")

        if not order_id:
            if DEBUG: logger.error(f"❌ [{stock_code}] 주문 응답 본문 오류 또는 주문번호(ODNO) 없음: {order_output}")
            post_to_slack(f"❌ 주문 응답 본문 오류: {stock_code}")
            return {"error": "주문 응답 본문 오류", "success": False}

        self.watch_orders[stock_code] = {
            "stock_code": stock_code,
            "order_id": order_id,
            "qty": qty,
            "ATR": atr,
            "price": price,
            "order_time": time.time(),
            "filled_qty": 0
        }

        if DEBUG: logger.debug(f"📊 현재 감시 중인 주문 수: {len(self.watch_orders)}")

        if DEBUG: logger.info(f"✅ [{stock_code}] 주문 성공 및 감시 등록 완료. 주문번호: {order_id}")

        return {
            "order_id": order_id,
            "stock_code": stock_code,
            "initial_qty": qty,
            "success": True,
            "message": f"[{stock_code}] 주문번호 {order_id} 감시 등록 완료."
        }

    async def handle_execution(self, order_no, stock_code, qty_filled, execution_price, execution_status):
        print(self.watch_orders)
        atr = self.watch_orders[stock_code]["atr"]

        """
        ✅ 실시간 체결 메시지를 기반으로 스톱로스를 계산하고 기록하는 함수

        - order_no: 주문번호
        - stock_code: 종목 코드
        - qty_filled: 체결 수량
        - execution_price: 체결 가격
        - execution_status: 체결 여부
        - atr: 평균 진폭 (기본값 5000)

        기능:
        - 체결 가격과 ATR을 바탕으로 스톱로스 가격을 계산
        - 계산된 스톱로스를 stoploss.json 파일에 기록
        """
        try:
            stoploss_multiplier = adjust_price_to_hoga(int(self.cfg.get("stoploss_atr", 2)))
            stoploss_price = adjust_price_to_hoga(int(execution_price) - (stoploss_multiplier * int(atr)))
            if DEBUG: logger.info(f"[ORDER] ✅ place_order_with_stoploss에서 stoploss 기록: {stock_code}, stoploss_price={stoploss_price}")
            self.record_stoploss(stock_code, stoploss_price, atr)

            # 한주라도 체결되면 해당종목의 호가, 체결 등록
            await self.websocket_manager.register_hoga(stock_code)
            await self.websocket_manager.register_execution_list(stock_code)

            # 체결 완료 후 체결통보 등록 해제
            await self.websocket_manager.unregister_execution_notice()
            if DEBUG:
                logger.info(f"[ORDER] ✅ 체결 완료, 체결통보 등록 해제")

        except Exception as e:
            if DEBUG: logger.exception(f"[ORDER] ❌ stoploss 기록 중 오류 발생 (place_order_with_stoploss): {e}")

    async def process_execution_queue(self):
        """
        🔁 주문 큐에 들어오는 작업들을 비동기로 처리하는 함수

        수신 항목:
        - stock_code: 종목 코드
        - qty: 주문 수량
        - price: 주문 가격
        - atr: 평균 진폭 (스톱로스 계산용)
        - order_type: 주문 유형 ("시장가", "지정가" 등)

        기능:
        - 큐로부터 주문 데이터를 수신하여 place_order_with_stoploss를 호출
        """
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

                if DEBUG: logger.debug(f"큐 작업 처리 시작: {task}")

                await self.place_order_with_stoploss(stock_code, qty, price, atr, order_type)

            except Exception as e:
                if DEBUG: logger.error(f"❌ 큐 처리 중 오류 발생: {e}", exc_info=True)

    async def handle_execution_notice_message(self, message: dict):
        """
        - WebSocket 체결통보 메시지를 처리하여 내부 로직으로 전달하는 함수
        - message: 실시간 체결통보 메시지 (dict 형태)
        기능:
        - 체결 메시지에서 필요한 변수 추출
        - 체결여부가 2일 경우에만 handle_execution() 호출
        """

        if DEBUG: logger.info(f"체결 통보 리스너 진입!!!!!")
        try:
            message_type = message.get("메시지타입")
            order_no = message.get("주문번호")
            stock_code = message.get("종목코드")
            stock_name = message.get("종목명")
            qty_filled = message.get("체결수량")
            execution_price = message.get("체결가격")
            execution_time = message.get("시간")
            order_type = message.get("주문구분")
            execution_status = message.get("체결여부")

            if DEBUG: logger.info(f"""
            [WS 체결 메시지 수신]
            ▶ 메시지타입: {message_type}
            ▶ 주문번호: {order_no} ▶ 종목코드: {stock_code} ▶ 종목명: {stock_name} ▶ 체결수량: {qty_filled}
            ▶ 체결가격: {execution_price} ▶ 시간: {execution_time} ▶ 주문구분: {order_type} ▶ 체결여부: {execution_status}
            """)

            if execution_status == "1":
                if DEBUG: logger.debug(f"[WS] 체결여부가 '1' (미체결) 상태로 확인되어 처리 생략: 주문번호={order_no}")
                return

            await self.handle_execution(order_no, stock_code, qty_filled, execution_price, execution_status)
        except Exception as e:
            if DEBUG: logger.error(f"❌ 실시간 체결 메시지 처리 중 오류 발생: {e}")

    async def handle_hoga_message(self, message: dict):
        # 실시간 종목별 호가 메시지 리스너
        if DEBUG:
            logger.info("종목별 호가 리스너 진입!!!!!")

        try:
            message_type = message.get("message_type")
            stock_code = message.get("종목코드")

            # 매수 호가, 잔량 리스트 생성
            ask_prices = [message.get(f"매수{i}호가") for i in range(1, 11)]
            ask_remains = [message.get(f"매수{i}호가잔량") for i in range(1, 11)]

            # 매도 호가, 잔량 리스트 생성
            bid_prices = [message.get(f"매도{i}호가") for i in range(1, 11)]
            bid_remains = [message.get(f"매도{i}호가잔량") for i in range(1, 11)]

            execution_time = message.get("체결시간")
            current_price = message.get("현재가")

            # 가장 첫 번째 매도, 매수 호가
            ask1 = ask_prices[0] if ask_prices else None
            bid1 = bid_prices[0] if bid_prices else None

            if DEBUG:
                logger.info(f"""
                [WS 체결 메시지 수신]
                ▶ 메시지타입: {message_type}
                ▶ 종목코드: {stock_code} ▶ 체결시간: {execution_time} ▶ 현재가: {current_price}
                ▶ 매도호가1: {ask1} ▶ 매수호가1: {bid1}
                """)

            # handle_execution 함수에 필요한 파라미터 넘기기 (필요에 맞게 조정)
            await self.handle_execution(
                message_type, stock_code,
                *ask_prices, *ask_remains,
                *bid_prices, *bid_remains,
                execution_time, current_price
            )
        except Exception as e:
            if DEBUG:
                logger.error(f"❌ 실시간 체결 메시지 처리 중 오류 발생: {e}")

    async def handle_execution_list_message(self, message: dict):
        # 실시간 종목별 체결 메시지 리스너
        if DEBUG: logger.info(f"종목별 체결 리스너 진입!!!!!")
        try:
            message_type = message.get("message_type")
            stock_code = message.get("종목코드")
            execution_time = message.get("체결시간")
            current_price = message.get("현재가")
            ask1 = message.get("매도호가1")
            bid1 = message.get("매수호가1")

            if DEBUG: logger.info(f"""
                    [WS 체결 메시지 수신]
                    ▶ 메시지타입: {message_type} ▶ 종목코드: {stock_code} ▶ 현재가: {current_price} ▶ 체결시간: {execution_time} 
                    ▶ 매도호가1: {ask1} ▶ 매수호가1: {bid1}
                    """)

            await self.handle_execution(stock_code, execution_time, current_price, ask1, bid1)
        except Exception as e:
            if DEBUG: logger.error(f"❌ 실시간 체결 메시지 처리 중 오류 발생: {e}")

    def record_stoploss(self, stock_code, stoploss_price, atr):
        """
        💾 stoploss.json 파일에 스톱로스 정보를 저장하는 함수

        - stock_code: 종목 코드
        - stoploss_price: 계산된 스톱로스 가격
        - atr: 평균 진폭

        기능:
        - 기존 stoploss.json 파일이 존재하면 불러옴
        - 해당 종목의 스톱로스 정보로 업데이트 후 저장
        """
        if DEBUG:logger.debug(f"[STOPLOSS] record_stoploss() 시작: stock_code={stock_code}, stoploss_price={stoploss_price}, atr={atr}")
        try:
            stoploss_data = {
                "stock_code": stock_code,
                "stoploss_price": stoploss_price,
                "atr": atr,
                "timestamp": time.time()
            }

            stoploss_path = os.path.join(CACHE_DIR, "stoploss.json")
            # Handle empty file case before json.load
            if os.path.exists(stoploss_path) and os.path.getsize(stoploss_path) > 0:
                with open(stoploss_path, "r", encoding="utf-8") as f:
                    stoploss_json = json.load(f)
            else:
                stoploss_json = {}

            stoploss_json[stock_code] = stoploss_data
            with open(stoploss_path, "w", encoding="utf-8") as f:
                json.dump(stoploss_json, f, indent=4, ensure_ascii=False)

            if DEBUG: logger.info(f"[STOPLOSS] 📝 stoploss 기록 완료: {stock_code} → {stoploss_price}")
            self.stoploss_cache.add(stock_code)
        except Exception as e:
            if DEBUG: logger.exception(f"[STOPLOSS] ❌ stoploss 저장 실패: {e}")
