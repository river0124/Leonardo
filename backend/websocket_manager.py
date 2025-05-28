import json
import websockets
import asyncio
import os
from typing import Set, Optional, Dict, Any

from loguru import logger
from utils import KoreaInvestEnv, KoreaInvestAPI
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode

# --- 상수 정의 ---
# WebSocket 메시지 타입 프리픽스
MSG_TYPE_REALTIME = '0'
MSG_TYPE_ENCRYPTED_NOTICE = '1'

# TR ID 상수
TR_ID_REALTIME_TICK = "H0STCNT0"  # 실시간 체결가
TR_ID_REALTIME_HOGA = "H0STASP0"  # 실시간 호가
TR_ID_SIGNING_NOTICE_REG = "H0STCNI0"  # 실시간 체결통보 등록 (일반)
TR_ID_SIGNING_NOTICE_REG_ETF = "H0STCNI9"  # 실시간 체결통보 등록 (ETF)
TR_ID_PINGPONG = "PINGPONG"

# 체결 통보 파싱 인덱스 (예시, 실제 API 문서와 일치시켜야 함)
# "고객ID|계좌번호|주문번호|원주문번호|매도매수구분|정정구분|주문종류2|단축종목코드|체결수량|체결단가|체결시간|거부여부|체결여부|접수여부|지점번호|주문수량|계좌명|체결종목명|해외종목구분|담보유형코드|담보대출일자|분할매수매도시작시간|분할매수매도종료시간|시간분할타입유형"
IDX_ACC_NO = 1
IDX_ORDER_NO = 2
IDX_ORIG_ORDER_NO = 3
IDX_BUY_SELL_GB = 4  # 매도매수구분 (01:매도, 02:매수)
IDX_CORRECT_GB = 5  # 정정구분
IDX_STOCK_CODE_SHORT = 8
IDX_EXEC_QTY = 9  # 체결수량
IDX_EXEC_PRICE = 10  # 체결단가
IDX_EXEC_TIME = 11  # 체결시간
IDX_REJECT_GB = 12  # 거부여부
IDX_EXEC_GB = 13  # 체결여부 (01:접수, 02:체결)
IDX_ORDER_QTY = 16
IDX_STOCK_NAME = 18

# IDX_ORDER_PRICE_ALT = 22 # 분할매수매도시작시간 - 주문가격으로 사용되는 부분은 API 확인 필요

class WebSocketManager:
    def __init__(self, korea_invest_api: KoreaInvestAPI, url: str):
        self.api: KoreaInvestAPI = korea_invest_api
        self.url: str = url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.aes_key: Optional[str] = None
        self.aes_iv: Optional[str] = None
        # self.api.account_num이 utils.KoreaInvestAPI에 정의되어 있다고 가정
        self.running_account_num: Optional[str] = getattr(self.api, 'account_num', None)
        if not self.running_account_num:
            logger.warning("API 객체에서 계좌번호(account_num)를 찾을 수 없습니다. 체결 통보 필터링이 제한될 수 있습니다.")
        self.stock_subscriptions: Set[str] = set()
        self.should_reconnect: bool = True
        self.is_connected: bool = False

    async def connect(self):
        logger.info(f"🔌 WebSocket 연결 시도 중... (URL: {self.url})")
        try:
            # ping_interval과 ping_timeout을 적절히 설정하여 연결 유지 및 감지
            async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as ws:
                self.websocket = ws
                self.is_connected = True
                logger.info("✅ WebSocket 연결 성공.")
                await self._subscribe_signing_notice()  # 체결 통보 구독 먼저
                # 기존 구독 종목 재구독 (필요시)
                # for stock_code in list(self.stock_subscriptions):
                #     await self.subscribe_stock(stock_code, is_reconnect=True)
                await self._listen()
        except websockets.exceptions.ConnectionClosedOK:
            logger.info("🚪 WebSocket 연결이 정상적으로 종료되었습니다.")
        except websockets.exceptions.ConnectionClosedError as e:
            logger.error(f"🚨 WebSocket 연결 오류로 종료됨: {e}")
        except ConnectionRefusedError:
            logger.error("🚫 WebSocket 연결 거부됨. 서버가 실행 중인지 확인하세요.")
        except Exception as e:
            logger.error(f"💥 WebSocket 연결 중 예외 발생: {e}", exc_info=True)
        finally:
            self.is_connected = False
            self.websocket = None
            if self.should_reconnect:
                logger.info("🔁 3초 후 WebSocket 재연결 시도...")
                await asyncio.sleep(3)
                asyncio.create_task(self.connect())  # 백그라운드에서 재연결 시도

    async def _send_message(self, message: str):
        if self.websocket and self.is_connected:
            try:
                await self.websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                logger.warning("📤 메시지 전송 중 연결 끊김 감지.")
                # 재연결 로직은 connect 메소드의 finally 블록에서 처리
        else:
            logger.warning("🌐 WebSocket이 연결되지 않아 메시지를 전송할 수 없습니다.")

    async def _subscribe_signing_notice(self):
        # self.api.get_send_data가 JSON 문자열을 반환한다고 가정
        send_data_json_str = self.api.get_send_data(cmd=7, stock_code=None)  # cmd 7: 체결통보 등록
        if send_data_json_str:
            await self._send_message(send_data_json_str)
            logger.info("✅ 체결통보(실시간 잔고) 구독 요청 전송 완료.")
        else:
            logger.error("❌ 체결통보 구독 메시지 생성 실패.")

    async def unsubscribe_signing_notice(self):
        """
        체결통보 해지 (cmd=8) 메서드
        """
        if self.websocket is None:
            logger.warning("🛑 웹소켓 연결이 되어 있지 않습니다.")
            return

        send_data = self.api.get_send_data(cmd=8, stock_code=None)
        await self._send_message(send_data)
        logger.debug("📴 체결통보 해지 요청 전송 완료")

    async def subscribe_stock(self, stock_code: str, is_reconnect: bool = False):
        if not is_reconnect and stock_code in self.stock_subscriptions:
            logger.debug(f"ℹ️ 종목 {stock_code}은(는) 이미 구독 중입니다.")
            return

        # cmd 5: 실시간 체결가, cmd 1: 실시간 호가 (API 문서에 따라 확인 필요)
        for cmd_type in [5, 1]:
            send_data_json_str = self.api.get_send_data(cmd=cmd_type, stock_code=stock_code)
            if send_data_json_str:
                await self._send_message(send_data_json_str)
                logger.info(f"📩 종목 구독 요청 CMD: {cmd_type}, 코드: {stock_code}")
            else:
                logger.error(f"❌ 종목 {stock_code} 구독 메시지(CMD:{cmd_type}) 생성 실패.")
        self.stock_subscriptions.add(stock_code)

    async def unsubscribe_stock(self, stock_code: str):
        if stock_code not in self.stock_subscriptions:
            logger.debug(f"ℹ️ 종목 {stock_code}은(는) 구독 중이 아닙니다.")
            return

        # cmd 4: 실시간 체결가 해제, cmd 2: 실시간 호가 해제 (API 문서에 따라 확인 필요)
        for cmd_type in [4, 2]:
            send_data_json_str = self.api.get_send_data(cmd=cmd_type, stock_code=stock_code)
            if send_data_json_str:
                await self._send_message(send_data_json_str)
                logger.info(f"📤 종목 구독 해제 요청 CMD: {cmd_type}, 코드: {stock_code}")
            else:
                logger.error(f"❌ 종목 {stock_code} 구독 해제 메시지(CMD:{cmd_type}) 생성 실패.")
        self.stock_subscriptions.discard(stock_code)

    async def _listen(self):
        logger.info("🎧 WebSocket 메시지 수신 대기 중...")
        while self.is_connected and self.websocket:
            try:
                data = await self.websocket.recv()
                if isinstance(data, str):
                    await self._handle_message(data)
                elif isinstance(data, bytes):  # 간혹 bytes로 오는 경우 처리
                    await self._handle_message(data.decode('utf-8'))
            except websockets.exceptions.ConnectionClosed:
                logger.warning("🚨 WebSocket 수신 중 연결 끊김 감지.")
                break  # _listen 루프 종료, connect 메소드의 finally에서 재연결 처리
            except Exception as e:
                logger.error(f"💥 메시지 수신/처리 중 예외 발생: {e}", exc_info=True)
                # 심각한 오류가 아니라면 계속 수신 시도
                await asyncio.sleep(1)  # 짧은 대기 후 계속

    def _aes_cbc_base64_dec(self, key: str, iv: str, cipher_text: str) -> str:
        try:
            cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
            return unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size).decode('utf-8')
        except Exception as e:
            logger.error(f"AES 복호화 실패: {e}", exc_info=True)
            return ""  # 복호화 실패 시 빈 문자열 반환

    def _parse_signing_notice(self, data: str) -> Optional[Dict[str, Any]]:
        if not self.aes_key or not self.aes_iv:
            logger.warning("AES 키/IV가 설정되지 않아 체결 통보를 복호화할 수 없습니다.")
            return None

        decrypted_str = self._aes_cbc_base64_dec(self.aes_key, self.aes_iv, data)
        if not decrypted_str:
            return None

        values = decrypted_str.split('^')
        # 필드 개수 최소 검증
        if len(values) < max(IDX_STOCK_NAME, IDX_ORDER_QTY, IDX_EXEC_PRICE) + 1:  # 필요한 최대 인덱스 + 1
            logger.warning(f"체결 통보 데이터 필드 개수 부족: {len(values)}개, 내용: {decrypted_str[:100]}...")
            return None

        try:
            account_no_recv = values[IDX_ACC_NO]
            # 계좌번호 필터링 (self.running_account_num이 설정된 경우)
            if self.running_account_num and account_no_recv[:8] != self.running_account_num[:8]:
                logger.trace(f"다른 계좌의 체결 통보 수신 무시: {account_no_recv}")
                return None

            reject_gb = values[IDX_REJECT_GB]
            if reject_gb != "0":  # 0: 정상
                logger.info(f"주문 거부 통보 수신: {values}")
                return {"type": "reject", "raw_data": values}

            exec_gb_val = values[IDX_EXEC_GB]
            exec_status = "알수없음"
            if exec_gb_val == "1":  # API 문서에는 01:접수, 02:체결로 되어있으나, 샘플은 1,2
                exec_status = "접수"
            elif exec_gb_val == "2":
                exec_status = "체결"

            # 정정구분(0:신규, 1:정정, 2:취소)과 매도매수구분(01:매도, 02:매수) 조합
            buy_sell_gb_val = values[IDX_BUY_SELL_GB]
            correct_gb_val = values[IDX_CORRECT_GB]
            order_gubun = "기타"

            if buy_sell_gb_val == "02":  # 매수
                if correct_gb_val == "0":
                    order_gubun = "매수"
                elif correct_gb_val == "1":
                    order_gubun = "매수정정"
                elif correct_gb_val == "2":
                    order_gubun = "매수취소"
            elif buy_sell_gb_val == "01":  # 매도
                if correct_gb_val == "0":
                    order_gubun = "매도"
                elif correct_gb_val == "1":
                    order_gubun = "매도정정"
                elif correct_gb_val == "2":
                    order_gubun = "매도취소"

            notice_data = {
                "type": "execution",
                "account_no": account_no_recv,
                "order_no": values[IDX_ORDER_NO],
                "original_order_no": values[IDX_ORIG_ORDER_NO],
                "order_type_detail": order_gubun,  # 상세 주문 구분
                "stock_code": values[IDX_STOCK_CODE_SHORT],
                "stock_name": values[IDX_STOCK_NAME],
                "exec_qty": int(values[IDX_EXEC_QTY]) if values[IDX_EXEC_QTY] else 0,
                "exec_price": int(values[IDX_EXEC_PRICE]) if values[IDX_EXEC_PRICE] else 0,
                "exec_time": values[IDX_EXEC_TIME],
                "exec_status": exec_status,  # "접수" 또는 "체결"
                "order_qty": int(values[IDX_ORDER_QTY]) if values[IDX_ORDER_QTY] else 0,
            }
            # 체결 시에만 체결가격/수량 의미 있음, 접수 시에는 주문가격/수량으로 해석될 수 있음 (API 확인)
            if exec_status == "접수":
                notice_data["order_price_on_accept"] = notice_data["exec_price"]  # 접수시 체결단가 필드는 주문단가일 수 있음
                notice_data["exec_price"] = 0  # 접수 상태이므로 실제 체결가는 0
                notice_data["exec_qty"] = 0  # 접수 상태이므로 실제 체결수량은 0

            return notice_data
        except IndexError as e:
            logger.error(f"체결 통보 파싱 중 IndexError: {e}. 데이터: {decrypted_str}", exc_info=True)
        except ValueError as e:
            logger.error(f"체결 통보 파싱 중 ValueError (숫자 변환 등): {e}. 데이터: {decrypted_str}", exc_info=True)
        return None

    def _parse_realtime_tick(self, data_str: str) -> Optional[Dict[str, Any]]:
        values = data_str.split('^')
        if len(values) < 3:  # 최소 필드 수 확인
            logger.warning(f"실시간 체결가 데이터 필드 부족: {data_str}")
            return None
        try:
            return {
                "type": "tick",
                "stock_code": values[0],
                "exec_time": values[1],
                "current_price": int(values[2]),
                # 필요한 경우 추가 필드 파싱
            }
        except ValueError:
            logger.error(f"실시간 체결가 현재가 변환 오류: {values[2]}", exc_info=True)
        except IndexError:
            logger.error(f"실시간 체결가 파싱 중 IndexError. 데이터: {data_str}", exc_info=True)
        return None

    def _parse_realtime_hoga(self, data_str: str) -> Optional[Dict[str, Any]]:
        values = data_str.split('^')
        # 호가 데이터는 필드가 많으므로, 필요한 최소 개수 확인 (예: 종목코드 + 10단계 호가 = 1 + 10*4 = 41개)
        if len(values) < 43:  # (종목코드 + (매도호가10+매도잔량10) + (매수호가10+매수잔량10) + 총매도/매수잔량 + 시간외총매도/매수잔량)
            logger.warning(f"실시간 호가 데이터 필드 부족: {data_str}")
            return None
        try:
            hoga_data = {"type": "hoga", "stock_code": values[0]}
            for i in range(1, 11):  # 10단계 호가
                hoga_data[f"ask_price_{i}"] = int(values[2 + i])  # 매도 i호가
                hoga_data[f"ask_volume_{i}"] = int(values[22 + i])  # 매도 i호가 잔량
                hoga_data[f"bid_price_{i}"] = int(values[12 + i])  # 매수 i호가
                hoga_data[f"bid_volume_{i}"] = int(values[32 + i])  # 매수 i호가 잔량
            # 총호가잔량 등 추가 정보 필요시 values 인덱스 참조하여 추가
            # values[1] : 호가시간
            # values[43]: 총매도호가잔량, values[44]: 총매수호가잔량
            # values[45]: 시간외총매도호가잔량, values[46]: 시간외총매수호가잔량
            return hoga_data
        except ValueError:
            logger.error(f"실시간 호가 가격/수량 변환 오류. 데이터: {data_str}", exc_info=True)
        except IndexError:
            logger.error(f"실시간 호가 파싱 중 IndexError. 데이터: {data_str}", exc_info=True)
        return None

    async def _handle_message(self, raw_data: str):
        logger.trace(f"Raw RCV: {raw_data}")
        try:
            if not raw_data: return

            if raw_data[0] == MSG_TYPE_REALTIME:  # 실시간 데이터 (체결, 호가 등)
                parts = raw_data.split('|', 3)  # 헤더1|헤더2|TRID|데이터
                if len(parts) < 4:
                    logger.warning(f"실시간 데이터 형식 오류 (구분자 부족): {raw_data}")
                    return

                tr_id = parts[1]  # 또는 parts[2]일 수 있음, API 문서 확인 필요. 샘플은 parts[1]
                data_content = parts[3]

                if tr_id == TR_ID_REALTIME_TICK:
                    parsed_data = self._parse_realtime_tick(data_content)
                    if parsed_data: logger.info(f"[실시간체결] {parsed_data}")
                elif tr_id == TR_ID_REALTIME_HOGA:
                    parsed_data = self._parse_realtime_hoga(data_content)
                    if parsed_data: logger.info(f"[실시간호가] {parsed_data}")
                else:
                    logger.debug(f"알 수 없는 실시간 TR_ID: {tr_id}, 데이터: {data_content}")

            elif raw_data[0] == MSG_TYPE_ENCRYPTED_NOTICE:  # 암호화된 체결 통보
                parts = raw_data.split('|', 3)
                if len(parts) < 4:
                    logger.warning(f"암호화된 체결 통보 형식 오류: {raw_data}")
                    return

                tr_id = parts[1]  # 또는 parts[2]
                encrypted_content = parts[3]

                if tr_id in (TR_ID_SIGNING_NOTICE_REG, TR_ID_SIGNING_NOTICE_REG_ETF):
                    parsed_notice = self._parse_signing_notice(encrypted_content)
                    if parsed_notice:
                        logger.info(f"[체결통보] {parsed_notice}")
                        # 여기서 parsed_notice를 다른 모듈이나 콜백으로 전달하여 처리 가능
                else:
                    logger.debug(f"알 수 없는 암호화 통보 TR_ID: {tr_id}")

            else:  # JSON 형식의 응답 (구독 결과, PINGPONG 등)
                try:
                    json_data = json.loads(raw_data)
                    header = json_data.get("header", {})
                    body = json_data.get("body", {})
                    tr_id = header.get("tr_id")

                    if tr_id == TR_ID_PINGPONG:
                        logger.debug("PINGPONG 수신, 응답 전송.")
                        await self._send_message(raw_data)  # PINGPONG은 그대로 응답
                    elif body.get("rt_cd") == '0':  # 정상 응답
                        logger.info(f"[응답정상] TR_ID: {tr_id}, MSG: {body.get('msg1')}")
                        if tr_id in (TR_ID_SIGNING_NOTICE_REG, TR_ID_SIGNING_NOTICE_REG_ETF):  # 체결통보 '등록' 응답
                            output = body.get("output", {})
                            self.aes_key = output.get("key")
                            self.aes_iv = output.get("iv")
                            if self.aes_key and self.aes_iv:
                                logger.info(f"🔑 AES KEY/IV 수신 완료. KEY: {self.aes_key[:5]}..., IV: {self.aes_iv[:5]}...")
                            else:
                                logger.error("❌ 체결통보 등록 응답에서 AES KEY/IV를 찾을 수 없습니다.")
                    else:  # 오류 응답
                        logger.error(
                            f"[응답오류] TR_ID: {tr_id}, CODE: {body.get('rt_cd')}, MSG: {body.get('msg1')}, DETAIL: {body.get('msg2', '')}")
                except json.JSONDecodeError:
                    logger.warning(f"JSON 파싱 실패: {raw_data}")
        except Exception as e:
            logger.error(f"메시지 핸들링 중 예외 발생: {e}. 원본 데이터: {raw_data}", exc_info=True)

    async def close(self):
        self.should_reconnect = False  # 재연결 중단
        if self.websocket and self.is_connected:
            logger.info("🔌 WebSocket 연결 종료 시도...")
            await self.websocket.close()
            self.is_connected = False
            logger.info("🚪 WebSocket 연결이 종료되었습니다.")


async def main():
    # --- 설정 로드 (실제 환경에서는 파일이나 환경변수에서 로드) ---
    # 이 부분은 utils.KoreaInvestEnv가 어떻게 설정(cfg)을 처리하는지에 따라 달라집니다.
    # cfg가 None이면 KoreaInvestEnv 내부에서 기본값을 사용하거나 오류를 발생시킬 수 있습니다.
    # 예시로 최소한의 cfg를 구성합니다.
    # 실제로는 flask_server.py의 load_settings와 유사한 방식으로 설정 파일을 로드해야 합니다.
    try:
        # 사용자가 지정한 경로로 변경
        settings_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/settings.json"
        logger.info(f"지정된 설정 파일 경로: {settings_path}")

        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                loaded_cfg = json.load(f)
            logger.info(f"{settings_path} 에서 설정 로드 성공.")
        else:
            logger.warning(f"{settings_path} 파일 없음. 기본 설정 사용 시도.")
            # 기본 설정 (API 키 등은 실제 값으로 채워야 함)
            loaded_cfg = {
                "is_paper_trading": True,  # 모의투자 여부
                "APP_KEY": "YOUR_APP_KEY",  # 실제 값으로 변경
                "APP_SECRET": "YOUR_APP_SECRET",  # 실제 값으로 변경
                "account_num_prefix": "YOUR_ACCOUNT_PREFIX",  # 실제 값으로 변경 (예: "50001234")
                # 기타 필요한 설정값들...
            }
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}. 기본값으로 진행합니다.")
        loaded_cfg = {"is_paper_trading": True, "APP_KEY": "", "APP_SECRET": ""}  # 최소한의 기본값

    env_cls = KoreaInvestEnv(loaded_cfg)  # KoreaInvestEnv가 cfg를 처리하도록
    base_headers = env_cls.get_base_headers()
    # get_full_config()가 토큰 발급 등 전체 설정을 반환한다고 가정
    full_cfg = env_cls.get_full_config()

    if not full_cfg.get("APP_KEY") or not full_cfg.get("APP_SECRET"):
        logger.error("API 키(APP_KEY, APP_SECRET)가 설정되지 않았습니다. 실행을 중단합니다.")
        return
    if not full_cfg.get("websocket_approval_key"):
        logger.error("웹소켓 접속키(websocket_approval_key)가 없습니다. API 통신을 확인하세요.")
        # return # 키가 없으면 접속 불가

    korea_invest_api = KoreaInvestAPI(cfg=full_cfg, base_headers=base_headers)
    # KoreaInvestAPI 인스턴스에 account_num 속성이 설정되어야 함
    # 예: korea_invest_api.account_num = full_cfg.get("account_num_prefix")

    ws_url_key = 'paper_websocket_url' if full_cfg.get('is_paper_trading', True) else 'websocket_url'
    websocket_url = full_cfg.get(ws_url_key)

    if not websocket_url:
        logger.error(f"WebSocket URL({ws_url_key})을 설정에서 찾을 수 없습니다.")
        return

    manager = WebSocketManager(korea_invest_api, websocket_url)

    try:
        # 예시: 특정 종목 구독
        # await manager.subscribe_stock("005930") # 삼성전자
        # await manager.subscribe_stock("000660") # SK하이닉스
        await manager.connect()  # 연결 및 수신 시작
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램 종료 요청.")
    finally:
        await manager.close()
        logger.info("WebSocket 매니저 종료 완료.")


if __name__ == "__main__":
    # 로그 레벨 설정 (예: DEBUG, INFO)
    # logger.add("websocket_manager.log", rotation="10 MB", level="DEBUG") # 파일 로깅 추가
    logger.remove()  # 기본 핸들러 제거
    logger.add(lambda msg: print(msg, end=''), colorize=True, level="INFO")  # 콘솔 출력 재설정

    asyncio.run(main())