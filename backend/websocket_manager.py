import asyncio
from loguru import logger
import os
import datetime
from settings import cfg
import websockets
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode

from utils import KoreaInvestEnv, KoreaInvestAPI
from trade_listener import TradeListener

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")

DEBUG = cfg.get("DEBUG", "False").lower() == "true"

websocket_manager = None

class SimpleListener:
    async def handle_ws_message(self, message):
        print(f"🔔 체결 통보 수신: {message}")

class Websocket_Manager:
    def __init__(self, cfg, approval_key):
        env_cls = KoreaInvestEnv(cfg)
        base_headers = env_cls.get_base_headers()
        cfg = env_cls.get_full_config()
        self.websocket_approval_key = approval_key
        self.korea_invest_api = KoreaInvestAPI(cfg, base_headers=base_headers, websocket_approval_key=approval_key)
        self.websockets_url = cfg['paper_websocket_url'] if cfg['is_paper_trading'] else cfg['websocket_url']
        self.is_paper = cfg["is_paper_trading"]
        self.should_run = True
        self.connection = None  # WebSocket connection attribute

    def set_listener(self, listener):
        self.listener = listener

    def stop(self):
        self.should_run = False

    async def run_websocket(self):
        self.should_run = True
        running_account_num = self.korea_invest_api.account_num
        aes_key, aes_iv = None, None
        logger.info("한국투자증권 API웹소켓 연결 시도!")
        async with websockets.connect(self.websockets_url, ping_interval=None) as websocket:
            cmd_register = 7 if self.is_paper else 5
            send_data_register_str = self.korea_invest_api.get_send_data(cmd=cmd_register)
            send_data_register = json.loads(send_data_register_str)
            send_data_register["approval_key"] = self.websocket_approval_key
            send_data_register = json.dumps(send_data_register)
            logger.info(f"📨 체결통보 등록 요청 전송: {send_data_register}, [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
            await websocket.send(send_data_register)
            logger.debug(f"📡 Websocket에 체결통보 등록 요청 데이터 전송 완료, [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

            while self.should_run:
                data = await websocket.recv()
                if data[0] == '0':
                    continue
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
                        if rt_cd == '1':
                            logger.info(f"### ERROR RETURN CODE [{rt_cd} MSG [{jsonObject['body']['msg1']}], [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
                        elif rt_cd == '0':
                            logger.info(f"### RETURN CODE [{rt_cd} MSG [{jsonObject['body']['msg1']}], [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
                            if trid in ("H0STCNI0", "H0STCNI9"):
                                aes_key = jsonObject["body"]["output"]["key"]
                                aes_iv = jsonObject["body"]["output"]["iv"]
                                logger.info(f"### TRID [{trid}] KEY[{aes_key}] IV[{aes_iv}], [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
                    else:
                        logger.info(f"### RECV [PINGPONG] [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
                        await websocket.send(data)
                        logger.info(f"### SEND [PINGPONG] [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

            # Unregister when done
            cmd_unregister = 8 if self.is_paper else 6
            send_data_unregister_str = self.korea_invest_api.get_send_data(cmd=cmd_unregister)
            send_data_unregister = json.loads(send_data_unregister_str)
            send_data_unregister["approval_key"] = self.websocket_approval_key
            send_data_unregister = json.dumps(send_data_unregister)
            logger.info(f"📨 체결통보 해제 요청 전송: {send_data_unregister}")
            await websocket.send(send_data_unregister)
            logger.info("✔ 체결통보 해제 요청 전송 완료.")

    def aes_cbc_base64_dec(self, key, iv, cipher_text):
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
        logger.debug(f"🛰 체결통보 수신 데이터 시작: {data}")
        # AES256 처리 단계
        aed_dec_str = Websocket_Manager.aes_cbc_base64_dec(key, iv, data)
        logger.debug(f"📦 AES 해독 데이터: {aed_dec_str}")
        values = aed_dec_str.split('^')
        계좌번호 = values[1] #
        if 계좌번호[:8] != account_num:
            return
        거부여부 = values[12]
        if 거부여부 != "0":
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
        logger.info(f"Received chejandata! 시간: {시간}, "
                    f"종목코드 : {종목코드}, 종목명: {종목명}, 주문수량: {주문수량}, "
                    f"주문가격 : {주문가격}, 체결수량: {체결수량}, 체결가격: {체결가격}, "
                    f"주문구분 : {주문구분}, 주문번호: {주문번호}, "
                    f"원주문번호 : {원주문번호}, 체결여부: {체결여부}")

        logger.debug(f"📬 체결 데이터 파싱 완료. Listener 존재 여부: {hasattr(self, 'listener')} | Listener 값: {self.listener}")
        logger.debug(f"📨 TradeManager → WebsocketManager 수신 확인: 체결데이터 전달 준비 중.")
        if hasattr(self, "listener") and self.listener:
            try:
                asyncio.create_task(self.listener.handle_ws_message({
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
                logger.error(f"❌ 리스너에 체결정보 전달 중 오류: {e}")

    def receive_realtime_hoga_domestic(self, data):
        """
        상세 메뉴는 아래의 링크 참조
        https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py
        """

        values = data.split('^') # 수신데이터를 split '^'
        data_dict = dict()
        data_dict["종목코드"] = values[0]
        for i in range(1,11):
            data_dict[f"매수{i}호가"] = values[i + 12]
            data_dict[f"매수{i}호가수량"] = values[i + 32]
            data_dict[f"매도{i}호가"] = values[2 + i]
            data_dict[f"매도{i}호가수량"] = values[22 + i]
        return data_dict

    def receive_realtime_tick_domestic(self,data):
        """
        메뉴 순서는 다음과 같음 '|'으로 분리해서 아래와 같이 하나씩 접근하면 죕니다.
        유가증권단축종목코드|주식체결시간|주식현재가|전일대비부호|전일대비|전일대비율|가중평균주식가격|주식시가|주식최고가|주식최저가|
        매도호가1|매수호가1|체결거래량|누적거래량|누적거래대금|매도체결건수|매수체결건수|순매수체결건수|체결강도|총매도수량|총매수수량|체결구분|
        매수비율|전일거래량대비등락율|시가시간|시가대비구분|시가대비|최고가시간|고가대비구분|고가대비|최저가시간|저가대비구분|저가대비|영업일자|
        신장운영구분코드|거래정지여부|매도호가잔량|매수호가잔량|총매도호가잔량|총매수호가잔량|거래량회전율|전일동시간누적거래량|전일동시간누적거래량비율|
        시간구분코드|임의종료구분코드|정적VI발동기준가
        """

        values = data.split('^')
        종목코드 = values[0]
        체결시간 = values[1]
        현재가 = int(values[2])
        return dict(
            종목코드 = 종목코드,
            체결시간 = 체결시간,
            현재가 = 현재가,
        )

    async def register_execution_notice(self, korea_invest_api, url):
        running_account_num = korea_invest_api.account_num
        aes_key, aes_iv = None, None
        logger.info("한국투자증권 API웹소켓 연결 시도!")
        async with websockets.connect(url, ping_interval=None) as websocket:
            cmd = 7 if self.is_paper else 5
            send_data = korea_invest_api.get_send_data(cmd=cmd, approval_key=self.websocket_approval_key)
            await websocket.send(send_data)
            # TODO: Consider adding timeout or disconnect logic to avoid infinite loop issues
            while True:
                data = await websocket.recv()
                if data[0] == '0':
                    pass
                elif data[0] == '1':
                    recvstr = data.split('|') # 수신데이터가 실데이터 이전은 '|'로 나뉘어져 있어 split
                    trid0 = recvstr[1]
                    if trid0 in ("H0STCNI0", "H0STCNI9"): #주식 체결 통보 처리
                        self.receive_signing_notice(recvstr[3], aes_key, aes_iv, running_account_num)

                else:
                    jsonObject = json.loads(data)
                    trid = jsonObject["header"]["tr_id"]

                    if trid != "PINGPONG":
                        rt_cd = jsonObject["body"]["rt_cd"]
                        if rt_cd == '1': #에러일 경우 처리
                            logger.info(f"### ERROR RETURN CODE [{rt_cd} MSG [{jsonObject['body']['msg1']}]")
                        elif rt_cd == '0': #정상일 경우 처리
                            logger.info(f"### RETURN CODE [{rt_cd} MSG [{jsonObject['body']['msg1']}]")
                            # 체결통보 처리를 위한 AES256 KEY, IV 처리 단계
                            if trid in ("H0STCNI0", "H0STCNI9"):
                                aes_key = jsonObject["body"]["output"]["key"]
                                aes_iv = jsonObject["body"]["output"]["iv"]
                                logger.info(f"### TRID [{trid}] KEY[{aes_key}] IV[{aes_iv}]")

                    elif trid == "PINGPONG":
                        logger.info(f"### RECV [PINGPONG] [{data}]")
                        await websocket.send(data)
                        logger.info(f"### SEND [PINGPONG] [{data}]")

    async def unregister_execution_notice(self,korea_invest_api, url):
        running_account_num = korea_invest_api.account_num
        aes_key, aes_iv = None, None
        logger.info("한국투자증권 API웹소켓 연결 시도!")
        async with websockets.connect(url, ping_interval=None) as websocket:
            cmd = 8 if self.is_paper else 6
            send_data = korea_invest_api.get_send_data(cmd=cmd, approval_key=self.websocket_approval_key)
            await websocket.send(send_data)
            # TODO: Consider adding timeout or disconnect logic to avoid infinite loop issues
            while True:
                data = await websocket.recv()
                if data[0] == '0':
                    pass
                elif data[0] == '1':
                    recvstr = data.split('|')  # 수신데이터가 실데이터 이전은 '|'로 나뉘어져 있어 split
                    trid0 = recvstr[1]
                    if trid0 in ("H0STCNI0", "H0STCNI9"):  # 주식 체결 통보 처리
                        self.receive_signing_notice(recvstr[3], aes_key, aes_iv, running_account_num)

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
                            if trid in ("H0STCNI0", "H0STCNI9"):
                                aes_key = jsonObject["body"]["output"]["key"]
                                aes_iv = jsonObject["body"]["output"]["iv"]
                                logger.info(f"### TRID [{trid}] KEY[{aes_key}] IV[{aes_iv}]")

                    elif trid == "PINGPONG":
                        logger.info(f"### RECV [PINGPONG] [{data}]")
                        await websocket.send(data)
                        logger.info(f"### SEND [PINGPONG] [{data}]")

    async def listen_forever(self, ws_url):
        async with websockets.connect(ws_url) as websocket:
            while True:
                msg = await websocket.recv()
                message = json.loads(msg)
                await TradeListener.handle_ws_message(message)

    async def send(self, message: dict):
        import json
        logger.debug(f"📡 [Websocket_Manager] send() 호출됨 - 메시지: {message}")
        if self.connection:
            await self.connection.send(json.dumps(message))
            logger.debug("✅ [Websocket_Manager] 메시지 전송 완료")
        else:
            logger.warning("⚠️ [Websocket_Manager] connection이 없습니다. 메시지 전송 실패")


# async def register_stock_monitoring(korea_invest_api, stock_code: str):
#     running_account_num = korea_invest_api.account_num
#     logger.info("한국투자증권 API웹소켓 연결 시도!")
#     send_data_ask = korea_invest_api.get_send_data(cmd=1, stock_code=stock_code)  # 호가
#     send_data_tick = korea_invest_api.get_send_data(cmd=3, stock_code=stock_code)  # 체결
#     await websocket.send(send_data_ask)
#     await websocket.send(send_data_tick)
#
# async def unregister_stock_monitoring(korea_invest_api, stock_code: str):
#     running_account_num = korea_invest_api.account_num
#     logger.info("한국투자증권 API웹소켓 연결 시도!")
#     send_data_ask = korea_invest_api.get_send_data(cmd=2, stock_code=stock_code)  # 호가 해제
#     send_data_tick = korea_invest_api.get_send_data(cmd=4, stock_code=stock_code)  # 체결 해제
#     await websocket.send(send_data_ask)
#     await websocket.send(send_data_tick)


def init_websocket_manager(cfg, websocket_approval_key):
    global websocket_manager
    websocket_manager = Websocket_Manager(cfg, websocket_approval_key)