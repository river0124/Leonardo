import json
import websockets
import asyncio

from loguru import logger
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode

from websockets.legacy.client import connect
from yaml import Loader


def run_websocket(korea_invenst_api, websocket_url):
    # 이벤트 루프 초기화
    loop = asyncio.get_event_loop()
    loop.run_until_complete(connect(korea_invenst_api,websocket_url))

def aes_cbc_base64_dec(key, iv, cipher_text):
    """
    :param key: str type AES256 secret key value
    :param iv: str type AES256 Initialize Vector
    :param cipher_text: Base64 encoded AES256 str
    :return: Base64-AES256 decodec str
    """
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    return bytes.decode(unpad(cipher.decrypt((b64decode(cipher_text)), AES.block_size)))

def receive_realtime_hoga_domestic(data):
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

    values = data.split('^')
    종목코드 = values[0]
    체결시간 = values[1]
    현재가 = int(values[2])
    return dict(
        종목코드 = 종목코드,
        체결시간 = 체결시간,
        현재가 = 현재가,
    )

async def connect (korea_invest_api, url):
    logger.info("한국투자증권 API웹소켓 연결 시도!")
    async with websockets.connect(url, ping_interval=None) as websocket:
        stock_code = "005930"
        send_data = korea_invest_api.get_send_data(cmd=3, stock_code=stock_code) #체결등록
        logger.info(f"[실시간 체결 등록] 종목코드: {stock_code}")
        await websockets.send(send_data)
        send_data = korea_invest_api.get_send_data(cmd=1, stock_code=stock_code) #호가등록
        logger.info(f"[실시간 호가 등록] 종목코드: {stock_code}")
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
                        send_data = korea_invest_api.get_send_data(cmd=4, stock_code=stock_code)
                        logger.info(f"[실시간 체결 해제] 종목코드: {stock_code}")
                        await websocket.send(send_data)
                elif trid0 == "H0STASP0": #주식 호가 데이터 처리
                    data_dict = receive_realtime_hoga_domestic(recvstr[3])
                    logger.info(f"주식 호가 데이터: {data_dict}")
                    send_data = korea_invest_api.get_send_data(cmd=2, stock_code=stock_code)
                    logger.info(f"[실시간 호가 해제] 종목코드: {stock_code}")



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
    run_websocket(korea_invest_api, websockets_url)