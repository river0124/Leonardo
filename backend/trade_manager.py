import os
import json
import time
from datetime import datetime, time as dt_time, timedelta  # timedelta 추가
import threading
import logging
from calculate_atr import calculate_atr
from slack_notifier import post_to_slack

# 로거 설정
logger = logging.getLogger(__name__)
# 기본 로깅 레벨 설정 (필요시 외부에서 상세 설정)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# 상수 정의
CACHE_DIR_NAME = "cache"
STOPLOSS_FILE_NAME = "stoploss.json"
# TRADE_LOG_FILE_NAME은 __init__에서 동적으로 결정됩니다.

ORDER_TYPE_LIMIT = "00"  # 지정가
ORDER_TYPE_MARKET = "01"  # 시장가

ATR_MULTIPLIER_STOPLOSS = 2
ATR_MULTIPLIER_TRAIL = 2

MARKET_OPEN_TIME = dt_time(8, 40)  # 장 시작 시간 (예: 정규장 시작 20분 전부터 감시 시작)
MARKET_CLOSE_TIME = dt_time(15, 31)  # 장 마감 시간 (예: 정규장 마감 1분 후까지 감시)


class TradeManager:
    def __init__(self, api, cfg):
        self.api = api
        logger.debug(f"[DEBUG] TradeManager에 전달된 API 인스턴스 타입: {type(api)}")
        self.cfg = cfg
        self.time_stop_days = cfg.get("time_stop_days", 3)
        logger.debug(f"⏱️ time_stop_days 설정값: {self.time_stop_days}")

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(self.base_dir, CACHE_DIR_NAME)
        self.stoploss_path = os.path.abspath(os.path.join(self.cache_dir, STOPLOSS_FILE_NAME))

        is_paper_trading = cfg.get("is_paper_trading", True)
        trade_log_filename = "paper_trade_log.json" if is_paper_trading else "real_trade_log.json"
        self.trade_log_path = os.path.join(self.cache_dir, trade_log_filename)

        os.makedirs(self.cache_dir, exist_ok=True)

        # Flask 서버에서 stop_event를 설정하고 스레드를 제어할 수 있도록 추가
        self.stop_event = threading.Event()

        # 주문 감시 큐 (체결 대기 주문)
        self.watch_orders = []

        # 로거 레벨 설정
        if self.cfg.get("DEBUG_MODE", False):
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        logger.info(f"TradeManager 초기화 완료. 모의투자: {is_paper_trading}, 로그파일: {self.trade_log_path}")

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

    def place_order_with_stoploss(self, stock_code, qty, price, atr, order_type=ORDER_TYPE_LIMIT, timeout=5):
        """
        지정가 주문 실행 후 주문 감시 큐에 등록 (체결 감시는 별도 스레드에서 처리)
        """
        logger.info(f"📤 [{stock_code}] {qty}주 주문 실행 (유형: {order_type}, 가격: {price}, ATR: {atr})")
        response = self.api.do_buy(stock_code, qty, price, order_type)
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

        logger.info(f"🆔 [{stock_code}] 주문번호: {order_id} → 감시 큐에 등록")
        self.watch_orders.append({
            "stock_code": stock_code,
            "order_id": order_id,
            "qty": qty,
            "atr": atr,
            "price": price,
            "order_time": time.time()
        })

        return {
            "order_id": order_id,
            "stock_code": stock_code,
            "initial_qty": qty,
            "success": True,
            "message": f"[{stock_code}] 주문번호 {order_id} 감시 등록 완료."
        }

    def monitor_order_fill(self):
        """
        감시 큐에 등록된 주문의 체결 여부를 주기적으로 확인하고, 체결 시 스톱로스 등록
        """
        logger.info("🛰️ 주문 체결 감시 쓰레드 시작됨")
        while not self.stop_event.is_set():
            for order in self.watch_orders[:]:  # 복사본 순회
                stock_code = order["stock_code"]
                order_id = order["order_id"]
                atr = order["atr"]
                qty = order["qty"]
                price = order.get("price", 0)

                # get_order_detail은 주문번호와 종목코드 모두 필요할 수 있음
                status = self.api.get_order_detail(order_id, stock_code)
                if status:
                    filled_qty = int(status.get("filled_qty", 0))
                    avg_price = float(status.get("avg_price", 0))
                    if filled_qty > 0:
                        logger.info(f"💰 [{stock_code}] {filled_qty}주 매수되었습니다. @ {avg_price}")
                        post_to_slack(f"💰 [{stock_code}] {filled_qty}주 매수되었습니다. @ {avg_price}")
                        self.setup_stoploss(stock_code, avg_price, atr, filled_qty)

                        if filled_qty >= qty:
                            logger.info(f"✅ [{stock_code}] 매수가 완료되었습니다.")
                            post_to_slack(f"✅ [{stock_code}] 매수가 완료되었습니다.")

                        self.watch_orders.remove(order)
            time.sleep(2)

    def setup_stoploss(self, code, entry_price, atr, qty, entry_time=None):
        """
        손절가 계산 및 stoploss.json 저장
        entry_time: 실제 진입 시간 (datetime 객체)
        """
        stop_loss_price = round(entry_price - ATR_MULTIPLIER_STOPLOSS * atr, 2)
        entry_time = entry_time or datetime.now()

        new_stoploss_entry = {
            code: {
                "entry_price": entry_price,
                "atr_at_entry": atr,  # 진입 시점의 ATR 기록
                "stop_loss_price": stop_loss_price,
                "quantity": qty,
                "active": True,
                "entry_timestamp": entry_time.timestamp(),  # Unix 타임스탬프로 저장
                "entry_datetime_str": entry_time.strftime("%Y-%m-%d %H:%M:%S"),  # 사람이 읽기 쉬운 형태
                "trail_active": False,
                "trail_high": entry_price,  # 트레일링 시작 시점의 최고가는 진입가로 초기화
                "last_atr_update_time": entry_time.timestamp()  # ATR 갱신 시간 추적용
            }
        }

        existing_data = self._read_json_file(self.stoploss_path, default_data={})

        if code in existing_data and existing_data[code].get("active", False):
            # 기존에 동일 종목의 활성 스톱로스가 있다면, 물타기(pyramiding) 또는 평균단가 조정 로직 필요
            # 여기서는 단순 덮어쓰기로 처리 (주의: 기존 포지션 정보 유실 가능성)
            logger.warning(f"⚠️ [{code}] 기존 활성 스톱로스 존재. 새 정보로 덮어씁니다. (수량: {existing_data[code]['quantity']} -> {qty})")

        existing_data.update(new_stoploss_entry)

        if self._write_json_file(self.stoploss_path, existing_data):
            logger.info(
                f"✅ [{code}] 스톱로스 저장 완료: 손절가 {stop_loss_price:.2f} (진입가: {entry_price:.2f}, ATR: {atr:.2f}, 수량: {qty})")
        else:
            logger.error(f"❌ [{code}] 스톱로스 저장 실패")

    def record_trade(self, code, entry_price, sell_price, qty, entry_time_dt, sell_time_dt, reason, pnl_amount=None,
                     pnl_percent=None):
        trade_log_path = self.trade_log_path

        if pnl_amount is None or pnl_percent is None:
            pnl_amount_calc = (sell_price - entry_price) * qty
            pnl_percent_calc = ((sell_price - entry_price) / entry_price * 100) if entry_price != 0 else 0
        else:  # API에서 제공하는 손익 사용 시
            pnl_amount_calc = pnl_amount
            pnl_percent_calc = pnl_percent

        log_entry = {
            "code": code,
            "buy_price": round(entry_price, 2),
            "sell_price": round(sell_price, 2),
            "qty": qty,
            "buy_date": entry_time_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "sell_date": sell_time_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "pnl_percent": round(pnl_percent_calc, 2),
            "pnl_amount": round(pnl_amount_calc, 2),
            "reason": reason
        }

        logs = self._read_json_file(trade_log_path, default_data=[])
        logs.append(log_entry)

        if self._write_json_file(trade_log_path, logs):
            logger.info(f"📝 [{code}] 트레이딩 로그 저장됨: {reason}, 손익: {pnl_amount_calc:.2f} ({pnl_percent_calc:.2f}%)")
        else:
            logger.error(f"❌ [{code}] 트레이딩 로그 저장 실패")

    def _get_current_price_safe(self, stock_code):
        current_price_data = self.api.get_current_price(stock_code)  # API 응답 객체라고 가정
        if not current_price_data or not current_price_data.is_ok():
            error_msg = current_price_data.get_error_message() if current_price_data else "API 응답 없음"
            logger.warning(f"⚠️ [{stock_code}] 현재가 조회 실패: {error_msg}")
            # post_to_slack(f"⚠️ 현재가 조회 실패: {stock_code} ({error_msg})") # 너무 잦은 알림 방지
            return None

        body = current_price_data.get_body()
        if not body:
            logger.warning(f"⚠️ [{stock_code}] 현재가 응답 본문 없음.")
            return None

        price_str = body.get("stck_prpr")  # 현재가 필드명
        if price_str is None:
            logger.warning(f"⚠️ [{stock_code}] 현재가 필드(stck_prpr) 없음. 응답: {body}")
            return None
        try:
            return float(price_str)
        except ValueError:
            logger.warning(f"⚠️ [{stock_code}] 현재가 형식 오류 (float 변환 불가): '{price_str}'")
            return None

    def _get_candle_data_safe(self, stock_code, days_for_volatility):
        """ 안전하게 캔들 데이터를 조회하고, KIS API 응답 형식에 맞게 처리 (가정) """
        # KIS API는 output1 (배열), output2 (객체) 등으로 응답이 나뉠 수 있음
        # 여기서는 get_candle_data가 이미 list of dicts (각 dict는 캔들)를 반환한다고 가정
        # 실제 API 응답 구조에 맞춰 파싱 필요
        try:
            # 예시: self.api.get_daily_candle(code, period_days=days_for_volatility)
            # 이 함수는 API 호출 후 [{ 'stck_hgpr': H, 'stck_lwpr': L, ...}, ...] 형태로 반환해야 함
            candle_response = self.api.get_candle_data(stock_code, days_for_volatility)  # 이 함수는 utils.py에 있어야 함

            if not candle_response or not candle_response.is_ok():
                logger.warning(f"⚠️ [{stock_code}] 캔들 데이터 API 조회 실패.")
                return None

            candles_output = candle_response.get_output1()  # KIS API는 output1에 배열 데이터가 오는 경우가 많음
            if not candles_output or not isinstance(candles_output, list):
                logger.warning(f"⚠️ [{stock_code}] 캔들 데이터 (output1)가 없거나 리스트가 아님: {candles_output}")
                return None

            # API 응답 필드명에 맞게 변환 (예: 'stck_hgpr' -> 'high', 'stck_lwpr' -> 'low')
            processed_candles = []
            for c in candles_output:
                try:
                    # KIS API는 가격 필드가 문자열로 올 수 있으므로 float 변환 필요
                    high = float(c.get('stck_hgpr', 0))  # 고가
                    low = float(c.get('stck_lwpr', 0))  # 저가
                    if high > 0 and low > 0:  # 유효한 데이터만 사용
                        processed_candles.append({'high': high, 'low': low})
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ [{stock_code}] 캔들 가격 데이터 변환 오류: {c}")
                    continue  # 다음 캔들로

            if not processed_candles:
                logger.warning(f"⚠️ [{stock_code}] 유효한 캔들 데이터가 없습니다.")
                return None
            return processed_candles

        except Exception as e:
            logger.error(f"⚠️ [{stock_code}] 캔들 데이터 조회/처리 중 예외: {e}", exc_info=True)
            return None

    def _handle_stoploss_or_trail(self, code, info, current_market_price, data_to_update):
        is_updated = False
        entry_price = float(info["entry_price"])
        initial_atr = float(info["atr_at_entry"])
        quantity = int(info["quantity"])
        entry_time_dt = datetime.fromtimestamp(info.get("entry_timestamp", time.time()))

        # Time-based stoploss (변동성 정체 시) - 일반 스톱로스 상태에서만 작동
        if not info.get("trail_active", False):
            # self.time_stop_days (예: 3)일 동안 변동성이 ATR의 특정 배수(예: 0.3) 미만이면 청산
            # 이 로직은 매일 한 번 또는 특정 주기로 실행하는 것이 더 효율적일 수 있음 (현재는 매초 확인)
            # 여기서는 단순화를 위해 _get_candle_data_safe를 호출

            # 너무 잦은 캔들 데이터 요청을 피하기 위해, 마지막 업데이트 시간으로부터 일정 시간 경과 시에만 확인
            # last_volatility_check_key = f"{code}_last_vol_check"
            # if time.time() - info.get(last_volatility_check_key, 0) > 3600: # 예: 1시간마다 변동성 체크

            candles = self._get_candle_data_safe(code, self.time_stop_days)  # 최근 N일치 캔들
            if candles and len(candles) >= self.time_stop_days:
                flat_day_count = 0
                volatility_threshold = initial_atr * 0.3  # 예: ATR의 30% 미만 변동성
                for candle_data in candles[:self.time_stop_days]:  # 최근 N일
                    daily_range = candle_data.get('high', 0) - candle_data.get('low', 0)
                    if daily_range > 0 and daily_range < volatility_threshold:
                        flat_day_count += 1

                if flat_day_count >= self.time_stop_days:
                    logger.info(
                        f"🕒 [{code}] 변동성 정체로 타임스톱 발동 (최근 {self.time_stop_days}일 중 {flat_day_count}일 변동성 부족). 현재가: {current_market_price:.2f}")
                    sell_response = self.api.do_sell(code, quantity, "0", ORDER_TYPE_MARKET)
                    if sell_response and sell_response.is_ok():
                        self.record_trade(code, entry_price, current_market_price, quantity, entry_time_dt,
                                          datetime.now(), "타임스톱(변동성부족)")
                        post_to_slack(f"🕒 타임스톱 매도: {code} {quantity}주 @ {current_market_price:.2f} (변동성 부족)")
                        data_to_update[code]["active"] = False
                        return True  # 매도 처리됨
                    else:
                        logger.error(f"❌ [{code}] 타임스톱 시장가 매도 실패.")
            # info[last_volatility_check_key] = time.time() # 마지막 변동성 체크 시간 업데이트

        # 트레일링 스탑 활성화 상태
        if info.get("trail_active"):
            # 트레일링 스탑 ATR 갱신 (예: 1시간마다)
            atr_for_trail = initial_atr  # 기본값은 진입 시 ATR
            if time.time() - info.get("last_atr_update_time", 0) > 3600:  # 1시간 경과 시
                latest_atr_val = calculate_atr(code, period=20, api_instance=self.api,
                                               return_only=True)  # calculate_atr에 api_instance 전달
                if latest_atr_val is not None and latest_atr_val > 0:
                    atr_for_trail = latest_atr_val
                    info["atr_current_trail"] = atr_for_trail  # 현재 트레일링에 사용된 ATR 기록 (선택적)
                    info["last_atr_update_time"] = time.time()
                    logger.debug(f"🔄 [{code}] 트레일링 ATR 갱신: {atr_for_trail:.2f}")
                else:
                    logger.warning(f"⚠️ [{code}] 트레일링용 최신 ATR 계산 실패, 이전 ATR 사용: {atr_for_trail:.2f}")
            else:  # 1시간 미경과 시 저장된 트레일링 ATR 사용 또는 초기 ATR 사용
                atr_for_trail = info.get("atr_current_trail", initial_atr)

            if current_market_price > info["trail_high"]:
                info["trail_high"] = current_market_price
                logger.info(f"📈 [{code}] 트레일링 최고가 갱신: {current_market_price:.2f}")
                is_updated = True

            trail_stop_price = round(info["trail_high"] - ATR_MULTIPLIER_TRAIL * atr_for_trail, 2)

            sell_reason = None
            if current_market_price <= trail_stop_price:
                sell_reason = "트레일링스톱"
                logger.info(
                    f"🔻 [{code}] {sell_reason} 발동. 현재가 {current_market_price:.2f} ≤ 트레일가 {trail_stop_price:.2f} (최고가: {info['trail_high']:.2f}, ATR: {atr_for_trail:.2f})")
            # elif current_market_price <= entry_price: # 선택적: 트레일링 중이라도 진입가 밑으로 내려가면 손절
            #     sell_reason = "트레일링중 진입가이탈"
            #     logger.info(f"🟥 [{code}] {sell_reason} 발동. 현재가 {current_market_price:.2f} ≤ 진입가 {entry_price:.2f}")

            if sell_reason:
                sell_response = self.api.do_sell(code, quantity, "0", ORDER_TYPE_MARKET)
                if sell_response and sell_response.is_ok():
                    self.record_trade(code, entry_price, current_market_price, quantity, entry_time_dt, datetime.now(),
                                      sell_reason)
                    post_to_slack(f"🔻 {sell_reason} 매도: {code} {quantity}주 @ {current_market_price:.2f}원")
                    data_to_update[code]["active"] = False
                    is_updated = True
                else:
                    logger.error(f"❌ [{code}] {sell_reason} 시장가 매도 실패.")
            return is_updated  # 매도했거나, 최고가 갱신했거나

        # 일반 스톱로스 상태
        else:
            stop_loss_price = float(info["stop_loss_price"])
            if current_market_price <= stop_loss_price:
                logger.info(f"🔻 [{code}] 손절 실행. 현재가 {current_market_price:.2f} ≤ 손절가 {stop_loss_price:.2f}")
                sell_response = self.api.do_sell(code, quantity, "0", ORDER_TYPE_MARKET)
                if sell_response and sell_response.is_ok():
                    self.record_trade(code, entry_price, current_market_price, quantity, entry_time_dt, datetime.now(),
                                      "손절(가격)")
                    post_to_slack(
                        f"🔻 손절 매도: {code} {quantity}주 @ {current_market_price:.2f} (손절가 {stop_loss_price:.2f})")
                    data_to_update[code]["active"] = False
                    is_updated = True
                else:
                    logger.error(f"❌ [{code}] 손절 시장가 매도 실패.")

            # 트레일링 스탑 전환 조건: 예: 진입가 + 1 * ATR 이상 수익 발생 시
            elif current_market_price >= entry_price + initial_atr:
                logger.info(
                    f"🚀 [{code}] 트레일링 스탑 전환 시작. 현재가: {current_market_price:.2f} (진입가: {entry_price:.2f}, ATR: {initial_atr:.2f})")
                info["trail_active"] = True
                info["trail_high"] = current_market_price  # 현재가를 초기 최고가로 설정
                info["last_atr_update_time"] = time.time()  # 트레일링 시작 시 ATR 갱신 시간 초기화
                post_to_slack(f"🚀 트레일링 전환: {code} @ {current_market_price:.2f}원 (진입가 + ATR)")
                is_updated = True

        return is_updated

    def monitor_stoploss(self):
        """
        stoploss.json을 주기적으로 체크하고 손절가 도달 시 자동 매도 실행
        스톱로스 → 트레일링스탑으로 전환 지원
        이 메소드는 외부 스레드에서 실행됩니다.
        """
        try:
            post_to_slack(f"📡 TradeManager 감시 시작됨 (PID: {os.getpid()}, Thread: {threading.get_ident()})")
            logger.info(f"📡 TradeManager 감시 스레드 시작. PID: {os.getpid()}, Thread: {threading.get_ident()}")
            last_hourly_market_status_log_time = None

            while not self.stop_event.is_set():  # 외부에서 스레드 종료 신호 확인
                now_dt = datetime.now()
                current_time = now_dt.time()

                if not (MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME):
                    if current_time.minute == 0 and current_time.second < 5:  # 매시 정각 근처에 한 번만 로그
                        if last_hourly_market_status_log_time is None or \
                                (now_dt - last_hourly_market_status_log_time).total_seconds() >= 3500:  # 약 1시간 간격
                            logger.info(
                                f"⏳ 시장 외 시간: {current_time}. 감시 일시 중단. (다음 확인까지 {(datetime.combine(now_dt.date(), MARKET_OPEN_TIME) - now_dt).total_seconds() if current_time < MARKET_OPEN_TIME else (datetime.combine(now_dt.date() + timedelta(days=1), MARKET_OPEN_TIME) - now_dt).total_seconds()} 초 남음)")
                            last_hourly_market_status_log_time = now_dt
                    # stop_event 확인 간격을 줄이기 위해 sleep 시간을 짧게 가져감
                    # time.sleep(1) 대신 self.stop_event.wait(timeout=1) 사용
                    if self.stop_event.wait(timeout=1):  # 1초 대기 또는 이벤트 발생 시 즉시 반응
                        break  # 이벤트 발생 시 루프 종료
                    continue

                # 시장 시간 내 로직
                stoploss_data = self._read_json_file(self.stoploss_path, default_data={})
                if not stoploss_data:
                    if not os.path.exists(self.stoploss_path):
                        # 파일이 아예 없을 때만 슬랙 알림 (너무 잦은 알림 방지)
                        # post_to_slack("⚠️ stoploss.json 파일이 없습니다. 감시 대기 중...")
                        logger.info("⚠️ stoploss.json 파일이 없습니다. 감시 대기 중...")
                    if self.stop_event.wait(timeout=1): break
                    continue

                data_changed_in_loop = False
                # stoploss_data.items()의 복사본을 순회하여 루프 중 변경에 안전하게 대응
                for code, info in list(stoploss_data.items()):
                    if self.stop_event.is_set(): break  # 각 종목 처리 전에도 종료 신호 확인

                    if not info.get("active", False):
                        continue

                    current_market_price = self._get_current_price_safe(code)
                    if current_market_price is None:
                        # 현재가 조회 실패 시 너무 많은 로그/알림 방지 (이미 _get_current_price_safe에서 로깅)
                        continue

                    if self._handle_stoploss_or_trail(code, info, current_market_price, stoploss_data):
                        data_changed_in_loop = True

                if self.stop_event.is_set(): break  # 모든 종목 처리 후 종료 신호 확인

                if data_changed_in_loop:
                    if not self._write_json_file(self.stoploss_path, stoploss_data):
                        logger.error("❌ 감시 루프 중 stoploss.json 업데이트 실패")
                        post_to_slack("❌ 감시 루프 중 stoploss.json 업데이트 실패")

                if self.stop_event.wait(timeout=1): break  # 작업 후 1초 대기 또는 이벤트 발생 시 즉시 반응

            logger.info(
                f"🚪 TradeManager 감시 스레드 정상 종료됨 (stop_event 수신). PID: {os.getpid()}, Thread: {threading.get_ident()}")
            post_to_slack(f"🚪 TradeManager 감시 종료됨 (PID: {os.getpid()}, Thread: {threading.get_ident()})")

        except Exception as e:
            logger.error(f"💥 TradeManager 감시 스레드에서 예외 발생: {e}", exc_info=True)
            post_to_slack(f"💥 TradeManager 감시 스레드 오류: {e}")
        finally:
            logger.info(
                f"🛑 TradeManager monitor_stoploss 스레드 finally 블록 실행. PID: {os.getpid()}, Thread: {threading.get_ident()}")

    def compute_conservative_total_asset(self):
        """
        예수금 + (보수적으로 계산한 평가금액)을 기반으로 총자산 계산
        스톱로스 또는 트레일 스탑 기준가로 계산
        """
        cash_balance = 0
        try:
            cash_response = self.api.get_cash()  # API가 응답 객체를 반환한다고 가정
            if cash_response and cash_response.is_ok():
                cash_body = cash_response.get_body()
                # 예수금 필드명 확인 필요 (예: 'dnca_tot_amt', 'nxdy_excc_amt' 등)
                # 여기서는 'dnca_tot_amt' (예수금총금액)을 사용한다고 가정
                cash_str = cash_body.get("dnca_tot_amt")
                if cash_str is not None:
                    cash_balance = float(cash_str)
                else:
                    logger.warning("⚠️ 예수금 필드(dnca_tot_amt) 없음. 예수금 0으로 처리.")
            else:
                error_msg = cash_response.get_error_message() if cash_response else "API 응답 없음"
                logger.warning(f"⚠️ 예수금 조회 실패: {error_msg}. 예수금 0으로 처리.")
        except Exception as e:
            logger.error(f"⚠️ 예수금 조회 중 예외 발생: {e}", exc_info=True)
            cash_balance = 0  # 예외 발생 시 0으로 처리

        total_conservative_asset = cash_balance
        stoploss_data = self._read_json_file(self.stoploss_path, default_data={})

        for code, info in stoploss_data.items():
            if not info.get("active", False):
                continue

            qty = int(info.get("quantity", 0))
            entry_price = float(info.get("entry_price", 0))
            # 평가 시 ATR은 진입 시점의 ATR을 사용하는 것이 일반적 (보수적)
            atr_at_entry = float(info.get("atr_at_entry", 0))

            base_price_for_eval = 0
            if info.get("trail_active", False):
                trail_high = float(info.get("trail_high", entry_price))
                # 트레일링 스탑 평가 시 ATR은 진입 시 ATR 또는 최근 갱신된 트레일링 ATR 사용 가능
                # 여기서는 보수적으로 진입 시 ATR 사용
                atr_for_trail_eval = float(info.get("atr_current_trail", atr_at_entry))
                trail_stop_price = trail_high - ATR_MULTIPLIER_TRAIL * atr_for_trail_eval
                # 평가 기준가는 현재 트레일링 스탑 가격으로. 단, 진입가보다 낮을 수 없음 (손실 확대 방지)
                base_price_for_eval = max(entry_price, trail_stop_price)
            else:
                # 일반 스톱로스 가격
                base_price_for_eval = float(
                    info.get("stop_loss_price", entry_price - ATR_MULTIPLIER_STOPLOSS * atr_at_entry))

            total_conservative_asset += qty * base_price_for_eval

        logger.info(f"💰 보수적 총 자산 계산: {total_conservative_asset:.2f} (예수금: {cash_balance:.2f})")
        return total_conservative_asset

    def export_risk_state(self):
        if not hasattr(self, 'stoploss_path') or not os.path.exists(self.stoploss_path):
            return {}

        stoploss_data = self._read_json_file(self.stoploss_path, default_data={})
        if not isinstance(stoploss_data, dict):
            return {}

        return {
            code: {
                "entry_price": data.get("entry_price"),
                "stop_price": data.get("stop_loss_price"),
                "trail_active": data.get("trail_active", False),
                "trail_high": data.get("trail_high", None),
                "last_atr_update_time": data.get("last_atr_update_time", None)
            }
            for code, data in stoploss_data.items()
        }