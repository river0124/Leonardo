import json
import websockets
import asyncio
import time

from loguru import logger
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode


def run_websocket(korea_invenst_api, websocket_url, stock_code):
    # 이벤트 루프 초기화
    loop = asyncio.get_event_loop()
    loop.run_until_complete(connect(korea_invenst_api, websocket_url, stock_code))

def aes_cbc_base64_dec(key, iv, cipher_text):
    """
    :param key: str type AES256 secret key value
    :param iv: str type AES256 Initialize Vector
    :param cipher_text: Base64 encoded AES256 str
    :return: Base64-AES256 decodec str
    """
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    return bytes.decode(unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size))

def receive_realtime_hoga_domestic(data):
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

def receive_realtime_tick_domestic(data):
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

async def connect (korea_invest_api, url, stock_code):
    logger.info("한국투자증권 API웹소켓 연결 시도!")
    async with websockets.connect(url, ping_interval=None) as websocket:
        send_data = korea_invest_api.get_send_data(cmd=5, stock_code=stock_code) #체결등록
        logger.info(f"[실시간 체결 등록] 종목코드: {stock_code}")
        await websocket.send(send_data)
        send_data = korea_invest_api.get_send_data(cmd=1, stock_code=stock_code) #호가등록
        logger.info(f"[실시간 호가 등록] 종목코드: {stock_code}")
        await websocket.send(send_data)

        await asyncio.sleep(30)
        send_data = korea_invest_api.get_send_data(cmd=4, stock_code=stock_code)  # 체결 해제
        logger.info(f"[30초 후 실시간 체결 해제] 종목코드: {stock_code}")
        await websocket.send(send_data)

        send_data = korea_invest_api.get_send_data(cmd=2, stock_code=stock_code)  # 호가 해제
        logger.info(f"[30초 후 실시간 호가 해제] 종목코드: {stock_code}")
        await websocket.send(send_data)

        while True:
            data = await websocket.recv()
            if data[0] == '0':
                recvstr = data.split('|') # 수신데이터가 실데이터 이전은 '|'로 나뉘어져 있어 split
                trid0 = recvstr[1]
                if trid0 == "H0STCNT0": #주식 체결 데이터 처리
                    data_cnt = int(recvstr[2]) #체결데이터 개수
                    for cnt in range(data_cnt):
                        data_dict = receive_realtime_tick_domestic(recvstr[3])
                        logger.info(f"주식 체결 데이터: {data_dict}")
                elif trid0 == "H0STASP0": # 주식호가 데이터 처리
                    data_dict = receive_realtime_hoga_domestic(recvstr[3])
                    logger.info(f"주식 호가 데이터: {data_dict}")

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
                            if trid in ("H0STCNT0", "H0STCNI9"):
                                aes_key = jsonObject["body"]["output"]["key"]
                                aes_iv = jsonObject["body"]["output"]["iv"]
                                logger.info(f"### TRID [{trid}] KEY[{aes_key}] IV[{aes_iv}]")

                    elif trid == "PINGPONG":
                        logger.info(f"### RECV [PINGPONG] [{data}]")
                        await websocket.send(data)
                        logger.info(f"### SEND [PINGPONG] [{data}]")

if __name__ == "__main__":
    import yaml
    from utils import KoreaInvestEnv, KoreaInvestAPI
    with open("./config.yaml", encoding='UTF-8') as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)
    env_cls = KoreaInvestEnv(cfg)
    base_headers = env_cls.get_base_headers()
    cfg = env_cls.get_full_config()
    korea_invest_api = KoreaInvestAPI(cfg, base_headers=base_headers)
    websockets_url = cfg['paper_websocket_url'] if cfg['is_paper_trading'] else cfg['websocket_url']
    stock_code = "005930"
    run_websocket(korea_invest_api, websockets_url, stock_code)