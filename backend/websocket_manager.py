import asyncio
from loguru import logger
import os
from dotenv import load_dotenv
from settings import cfg
import websockets
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode
from binascii import unhexlify
import traceback

load_dotenv()
DEBUG = cfg.get("DEBUG", "False") == "True"
CACHE_DIR = os.getenv('CACHE_DIR')
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")
STOPLOSS_FILE_NAME = os.path.join(CACHE_DIR, "stoploss.json")

class Websocket_Manager:
    def __init__(self, cfg, api, execution_queue=None):
        self.cfg = cfg
        self.api = api
        self.order_queue = execution_queue
        self.websockets_url = cfg['paper_websocket_url'] if cfg['is_paper_trading'] else cfg['websocket_url']
        self.is_paper = cfg["is_paper_trading"]
        self.listener = None
        self._running = False
        self.aes_key = None
        self.aes_iv = None
        self.execution_registered = False
        self.websocket = None
        # Initialize execution_notices as an empty set
        self.execution_notices = set()

    def aes_cbc_base64_dec(key, iv, cipher_text):
        """
        :param key: str type AES256 secret websocket_example2.pykey value
        :param iv: str type AES256 Initialize Vector
        :param cipher_text: Base64 encoded AES256 str
        :return: Base64-AES256 decodec str
        """
        cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        return bytes.decode(unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size))

    def receive_signing_notice(self, data, key, iv, account_num=''):
        """
        "고객 ID|계좌번호|주문번호|원주문번호|매도매수구분|정정구분|주문종류2|단축종목코드|체결수량|체결단가|체결시간|거부여부|체결여부|접수여부|지점번호|주문수량|계좌명|체결종목명|해외종목구분|담보유형코드|담보대출일자|분할매수매도시작시간|분할매수매도종료시간|시간분할타입유형"
        """
        if not data:
            logger.error("❌ 수신된 데이터 없음")
            return

        try:
            aed_dec_str = Websocket_Manager.aes_cbc_base64_dec(key, iv, data)
            values = aed_dec_str.split('^')
            if len(values) < 23:
                logger.error("❌ 복호화 후 values 길이 부족 - 처리 중단")
                return
        except Exception as e:
            logger.error(f"❌ 복호화 중 예외 발생: {e}")
            return

        if DEBUG:
            logger.debug(f"🛰 체결통보 수신 데이터 시작: {data}")
            logger.debug(f"📦 AES 해독 데이터: {aed_dec_str}")
        계좌번호 = values[1] #
        if 계좌번호[:8] != account_num:
            return
        거부여부 = values[12]
        if 거부여부 != "0":
            if DEBUG:
                logger.info(f"Got 거부 TR!")
            return
        체결여부 = values[13]
        if 체결여부 == "01":
            체결여부 = "접수"
        elif 체결여부 == "02":
            체결여부 = "체결"
        종목코드 = values[8]
        종목명 = values[18]
        시간 = values[11]
        주문수량 = 0 if len(values[16]) == 0 else int(values[16])
        if values[13] == '1':
            주문가격 = 0 if len(values[10]) == 0 else int(values[10])
        else:
            주문가격 = 0 if len(values[22]) == 0 else int(values[22])
        체결수량 = 0 if len(values[9]) == 0 or 체결여부 == "1" else int(values[9])
        if values[13] == '1':
            체결가격 = 0
        else:
            체결가격 = 0 if len(values[10]) == 0 else int(values[10])
        매도매수구분 = values[4]
        정정구분 = values[5]
        if 매도매수구분 == "02" and 정정구분 != "0":
            주문구분 = "매수정정"
        elif 매도매수구분 == "01" and 정정구분 != "0":
            주문구분 = "매도정정"
        elif 매도매수구분 == "02":
            주문구분 = "매수"
        elif 매도매수구분 == "01":
            주문구분 = "매도"
        else:
            raise ValueError(f"주문구분 실패! 매도매수구분: {매도매수구분}, 정정구분: {정정구분}")

        주문번호 = values[2]
        원주문번호 = values[3]
        if DEBUG:
            logger.info(f"Received chejandata! 시간: {시간}, "
                        f"종목코드 : {종목코드}, 종목명: {종목명}, 주문수량: {주문수량}, "
                        f"주문가격 : {주문가격}, 체결수량: {체결수량}, 체결가격: {체결가격}, "
                        f"주문구분 : {주문구분}, 주문번호: {주문번호}, "
                        f"원주문번호 : {원주문번호}, 체결여부: {체결여부}")

        if DEBUG:
            logger.debug(f"📬 체결 데이터 파싱 완료. Listener 존재 여부: {hasattr(self, 'listener')} | Listener 값: {self.listener}")
            logger.debug(f"📨 TradeManager → WebsocketManager 수신 확인: 체결데이터 전달 준비 중.")
        if hasattr(self, "listener") and self.listener:
            try:
                asyncio.create_task(self.listener.handle_execution_notice_message({
                    "종목코드": 종목코드,
                    "종목명": 종목명,
                    "체결수량": 체결수량,
                    "체결가격": 체결가격,
                    "시간": 시간,
                    "주문번호": 주문번호,
                    "원주문번호": 원주문번호,
                    "주문구분": 주문구분,
                    "체결여부": 체결여부,
                }))
            except Exception as e:
                if DEBUG:
                    logger.error(f"❌ 리스너에 체결통보 정보 전달 중 오류: {e}")

    async def receive_realtime_hoga_domestic(self, data):
        """
        상세 메뉴는 아래의 링크 참조
        https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py
        """

        values = data.split('^')  # 수신데이터를 split '^'
        data_dict = dict()
        data_dict["종목코드"] = values[0]
        for i in range(1, 11):
            data_dict[f"매수{i}호가"] = values[i + 12]
            data_dict[f"매수{i}호가수량"] = values[i + 32]
            data_dict[f"매도{i}호가"] = values[2 + i]
            data_dict[f"매도{i}호가수량"] = values[22 + i]

        print(data_dict)

        if self.listener:
            try:
                asyncio.create_task(self.listener.handle_hoga_message(data_dict))
            except Exception as e:
                if DEBUG:
                    logger.error(f"❌ 리스너에 호가정보 전달 중 오류: {e}")

        if DEBUG:
            logger.info(f"주식 호가 데이터: {data_dict}")

        return data_dict

    async def receive_realtime_tick_domestic(self, data):
        """
        메뉴 순서는 다음과 같음 '|'으로 분리해서 아래와 같이 하나씩 접근하면 죕니다.
        유가증권단축종목코드|주식체결시간|주식현재가|전일대비부호|전일대비|전일대비율|가중평균주식가격|주식시가|주식최고가|주식최저가|
        매도호가1|매수호가1|체결거래량|누적거래량|누적거래대금|매도체결건수|매수체결건수|순매수체결건수|체결강도|총매도수량|총매수수량|체결구분|
        매수비율|전일거래량대비등락율|시가시간|시가대비구분|시가대비|최고가시간|고가대비구분|고가대비|최저가시간|저가대비구분|저가대비|영업일자|
        신장운영구분코드|거래정지여부|매도호가잔량|매수호가잔량|총매도호가잔량|총매수호가잔량|거래량회전율|전일동시간누적거래량|전일동시간누적거래량비율|
        시간구분코드|임의종료구분코드|정적VI발동기준가
        """
        values = data.split('^')
        data_dict = dict()

        data_dict["종목코드"] = values[0]
        data_dict["체결시간"] = values[1]
        data_dict["현재가"] = int(values[2])
        data_dict["매도호가1"] = int(values[10])
        data_dict["매수호가1"] = int(values[11])

        print(data_dict)

        if self.listener:
            try:
                asyncio.create_task(self.listener.handle_execution_list_message(data_dict))
            except Exception as e:
                if DEBUG:
                    logger.error(f"❌ 리스너에 체결정보 전달 중 오류: {e}")

        if DEBUG:
            logger.info(f"주식 호가 데이터: {data_dict}")

        return data_dict

    async def websocket_listen_init(self, korea_invest_api, url, cmd, stock_code):
        running_account_num = korea_invest_api.account_num
        aes_key, aes_iv = None, None

        CMD_MEANING = {
            1: "호가 등록",
            2: "호가 해제",
            3: "체결 등록",
            4: "체결 해제",
            5: "실전 체결통보 등록",
            6: "실전 체결통보 해제",
            7: "모의 체결통보 등록",
            8: "모의 체결통보 해제",
        }

        if DEBUG: logger.info(f"웹소켓 연결 시도 - 명령 cmd: {cmd} ({CMD_MEANING[cmd]})")

        async with websockets.connect(url, ping_interval=None) as websocket:
            send_data = korea_invest_api.get_send_data(cmd=cmd, stock_code=stock_code)
            await websocket.send(send_data)

            while True:
                data = await websocket.recv()

                if data[0] == '0':
                    recvstr = data.split('|')  # 수신데이터가 실데이터 이전은 '|'로 나뉘어져 있어 split
                    trid0 = recvstr[1]
                    if trid0 == "H0STCNT0":  # 주식 체결 데이터 처리
                        data_cnt = int(recvstr[2])  # 체결데이터 개수
                        for cnt in range(data_cnt):
                            data_dict = await self.receive_realtime_tick_domestic(recvstr[3])
                            logger.info(f"주식 체결 데이터: {data_dict}")
                    elif trid0 == "H0STASP0":  # 주식호가 데이터 처리
                        data_dict = await self.receive_realtime_hoga_domestic(recvstr[3])
                        logger.info(f"주식 호가 데이터: {data_dict}")

                    else:
                        jsonObject = json.loads(data)
                        trid = jsonObject["header"]["tr_id"]

                        if trid != "PINGPONG":
                            rt_cd = jsonObject["body"]["rt_cd"]
                            if rt_cd == '1':  # 에러일 경우 처리
                                logger.info(f"### ERROR RETURN CODE [{rt_cd} MSG [{jsonObject['body']['msg1']}]")
                            elif rt_cd == '0':  # 정상일 경우 처리
                                logger.info(f"### RETURN CODE [{rt_cd} MSG [{jsonObject['body']['msg1']}]")
                                # 체결통보 처리를 위한 AES256 KEY, IV 처리 단계
                                if trid in ("H0STCNT0", "H0STCNI9"):
                                    aes_key = jsonObject["body"]["output"]["key"]
                                    aes_iv = jsonObject["body"]["output"]["iv"]
                                    logger.info(f"### TRID [{trid}] KEY[{aes_key}] IV[{aes_iv}]")

                        elif trid == "PINGPONG":
                            logger.info(f"### RECV [PINGPONG] [{data}]")
                            await websocket.send(data)
                            logger.info(f"### SEND [PINGPONG] [{data}]")

                elif data[0] == '1':
                    recvstr = data.split('|')
                    trid0 = recvstr[1]
                    if trid0 in ("H0STCNI0", "H0STCNI9"):
                        self.receive_signing_notice(recvstr[3], aes_key, aes_iv, running_account_num)

                else:
                    jsonObject = json.loads(data)
                    trid = jsonObject["header"]["tr_id"]

                    if trid != "PINGPONG":
                        rt_cd = jsonObject["body"]["rt_cd"]
                        if rt_cd == '1':  # 에러 처리
                            if DEBUG:
                                logger.info(f"### ERROR RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
                        elif rt_cd == '0':  # 정상 처리
                            if DEBUG:
                                logger.info(f"### RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
                            if trid in ("H0STCNI0", "H0STCNI9"):
                                aes_key = jsonObject["body"]["output"]["key"]
                                aes_iv = jsonObject["body"]["output"]["iv"]
                                if DEBUG:
                                    logger.info(f"### TRID [{trid}] KEY[{aes_key}] IV[{aes_iv}]")
                    else:
                        if DEBUG:
                            logger.info(f"### RECV [PINGPONG] [{data}]")
                        await websocket.send(data)
                        if DEBUG:
                            logger.info(f"### SEND [PINGPONG] [{data}]")

    async def register_execution_notice(self):
        # 실시간 체결 통보 등록
        if self.execution_registered:
            if DEBUG: logger.warning("🛑 이미 체결통보가 등록되어 있어 기존 세션 종료 시도 중")
            if self.websocket is not None:
                await self.websocket.close()
                if DEBUG: logger.info("🔌 기존 웹소켓 연결 종료 완료")
            self.execution_registered = False

        stock_code = None
        await self.websocket_listen_init(self.api, self.websockets_url, 7 if self.is_paper else 5, stock_code)
        if DEBUG: logger.info("실시간 체결통보 등록 요청 전송 완료")
        self.execution_registered = True

    async def unregister_execution_notice(self):
        # 실시간 체결 통보 해제
        stock_code = None
        await self.websocket_listen_init(self.api, self.websockets_url, 8 if self.is_paper else 6, stock_code)
        if DEBUG: logger.info("실시간 체결통보 해제 요청 전송 완료")
        self.execution_registered = False

    async def register_hoga(self, stock_code):
        # 특정 종목 실시간 주식 호가 등록
        await self.websocket_listen_init(self.api, self.websockets_url, 1, stock_code)
        if DEBUG: logger.info(f"{stock_code}: 실시간 호가정보 등록 요청 전송 완료")

    async def unregister_hoga(self, stock_code):
        # 특정 종목 실시간 주식 호가 해제
        await self.websocket_listen_init(self.api, self.websockets_url, 2, stock_code)
        if DEBUG: logger.info(f"{stock_code}: 실시간 체결정보 등록 요청 전송 완료")

    async def register_execution_list(self, stock_code):
        # 특정 종목 실시간 주식체결 등록
        await self.websocket_listen_init(self.api, self.websockets_url, 3, stock_code)
        if DEBUG: logger.info(f"{stock_code}: 실시간 체결정보 등록 요청 전송 완료")

    async def unregister_execution_list(self, stock_code):
        # 특정 종목 실시간 주식체결 해제
        await self.websocket_listen_init(self.api, self.websockets_url, 4, stock_code)
        if DEBUG: logger.info(f"{stock_code}: 실시간 체결정보 등록 요청 전송 완료")

    async def _handle_incoming(self, data, aes_key, aes_iv, running_account_num):
        if DEBUG:
            logger.debug(f"📨 [WebSocketManager] 수신 메시지: {data}")
        if data[0] == '0':
            return
        elif data[0] == '1':
            recvstr = data.split('|')
            trid0 = recvstr[1]
            if trid0 in ("H0STCNI0", "H0STCNI9"):
                if not self.aes_key or not self.aes_iv:
                    if DEBUG:
                        logger.warning("⚠️ AES KEY/IV 없음 → 체결 통보 무시")
                    return
                try:
                    self.receive_signing_notice(recvstr[3], self.aes_key, self.aes_iv, running_account_num)
                except Exception as e:
                    if DEBUG:
                        logger.error(f"❌ 체결통보 처리 중 오류: {e}")
                        logger.error(traceback.format_exc())
        else:
            jsonObject = json.loads(data)
            trid = jsonObject["header"]["tr_id"]

            if trid != "PINGPONG":
                rt_cd = jsonObject["body"]["rt_cd"]
                if rt_cd == '1':
                    if DEBUG:
                        logger.info(f"### ERROR RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
                elif rt_cd == '0':
                    if DEBUG:
                        logger.info(f"### RETURN CODE [{rt_cd}] MSG [{jsonObject['body']['msg1']}]")
                    if trid in ("H0STCNI0", "H0STCNI9"):
                        self.aes_key = jsonObject["body"]["output"]["key"]
                        self.aes_iv = jsonObject["body"]["output"]["iv"]
                        if DEBUG:
                            logger.info(f"### TRID [{trid}] KEY[{self.aes_key}] IV[{self.aes_iv}]")
            else:
                if DEBUG:
                    logger.info(f"### RECV [PINGPONG]")
                await self.websocket.send(data)
                if DEBUG:
                    logger.info(f"### SEND [PINGPONG]")

    def stop(self):
        self._running = False