import json
import time
import pandas as pd
import requests
from loguru import logger
import os
from dotenv import load_dotenv, dotenv_values
from collections import namedtuple

BASE_DIR = os.getenv('BASE_DIR', os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.getenv('CACHE_DIR', os.path.join(BASE_DIR, 'cache'))
SETTINGS_FILE = os.getenv('SETTINGS_FILE', os.path.join(CACHE_DIR, 'settings.json'))
load_dotenv()

with open(os.path.join(CACHE_DIR, "settings.json"), "r", encoding="utf-8") as f:
    settings_vars = json.load(f)
DEBUG = settings_vars.get("DEBUG", "False").lower() == "true"

# 로그 경로를 현재 파일(__file__) 기준으로 안전하게 구성
LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "trading_{time:YYYY-MM-DD}.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# 로그 파일 설정
logger.add(LOG_PATH, rotation="10 MB", retention="10 days", encoding="utf-8", enqueue=True)

class KoreaInvestEnv:
    def __init__(self):
        settings_path = os.path.join(CACHE_DIR, "settings.json")
        with open(settings_path, "r", encoding="utf-8") as f:
            settings_vars = json.load(f)

        env_vars = dotenv_values('.env')
        cfg = {**settings_vars, **env_vars}
        self.cfg = cfg
        self.base_headers = {
            "content_Type": "application/json; charset=utf-8",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User_Agent": self.cfg.get("user_agent", "")
        }

        self.is_paper_trading = self.cfg.get("is_paper_trading")

        # 1. 토큰 선택
        if self.is_paper_trading:
            self.access_token = cfg["papertoken"]
            self.account_num = cfg["paper_stock_account_number"]
            token_issued_at = self.cfg.get("papertoken_issued_at", 0)
        else:
            self.access_token = cfg["realtoken"]
            self.account_num = cfg["stock_account_number"]
            token_issued_at = self.cfg.get("realtoken_issued_at", 0)
        self.token_issued_at = token_issued_at  # <-- Add this line

        # 2. 현재 시간과 토큰 발급 시간 차이 체크 (23시간 = 82800초)
        current_time = int(time.time())
        if current_time - token_issued_at > 82800:  # 23시간 이상 경과
            if DEBUG:
                logger.info("⌛ 토큰 발급 후 23시간 경과, refresh_access_token 호출 예정")
            self.refresh_access_token()  # 나중에 정의할 함수

        # 3. 헤더 초기 설정
        self.base_headers["authorization"] = self.access_token
        self.request_base_url = cfg["paper_url"] if self.is_paper_trading else cfg["url"]
        websocket_approval_key = cfg.get("websocket_approval_key")
        if not websocket_approval_key:
            logger.warning("❗ cfg에 approval_key 없음 – 직접 발급 시도")
            websocket_approval_key = self.get_websocket_approval_key()
        self.cfg["websocket_approval_key"] = websocket_approval_key

    @classmethod
    def get_env_keys_list(cls):
        env_vars = dotenv_values('.env')
        return list(env_vars.keys())

    def get_base_headers(self):
        headers = self.base_headers.copy()
        # Always use the access_token from cfg (already set in self.access_token)
        headers["authorization"] = self.access_token
        return headers

    def get_websocket_approval_key(self):
        logger.debug("[get_websocket_approval_key] 🔁 함수 호출됨")

        if self.is_paper_trading:
            api_key = self.cfg["paper_api_key"]
            api_secret_key = self.cfg["paper_api_secret_key"]
            base_url = self.cfg["paper_url"]
        else:
            api_key = self.cfg["api_key"]
            api_secret_key = self.cfg["api_secret_key"]
            base_url = self.cfg["url"]

        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": api_key,
            "secretkey": api_secret_key
        }

        res = requests.post(base_url, headers=headers, data=json.dumps(body))

        try:
            data = res.json()
        except Exception as e:
            logger.error(f"❌ JSON 파싱 실패: {e}, 응답 텍스트: {res.text}")
            return None

        logger.info(f"📦 승인 응답 데이터: {data}")
        # 파일에 현재 cfg를 저장하는 코드 추가
        self.cfg["websocket_approval_key"] = data.get("approval_key", "")
        logger.info(f"✅ websocket_approval_key를 cfg에 저장 완료: {self.cfg['websocket_approval_key']}")

        # settings.json 파일 경로 정의
        settings_path = os.path.join(BASE_DIR, "cache", "settings.json")
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ settings.json에 websocket_approval_key 갱신 저장 완료: {settings_path}")
        except Exception as e:
            logger.error(f"❌ settings.json 저장 실패: {e}")

        if res.status_code != 200:
            logger.error(f"❌ [웹소켓 승인 요청 실패] HTTP {res.status_code} - {data}")
            return None

        if "approval_key" not in data:
            logger.error(f"❌ approval_key 누락 - 응답 데이터: {data}")
            return None

        return data

    def refresh_access_token(self):
        #토큰 발급 URL
        if self.is_paper_trading:
            token_url = self.cfg.get("paper_url") + "/oauth2/tokenP"
            api_key = self.cfg.get("paper_api_key")
            api_secret_key = self.cfg.get("paper_api_secret_key")
        else:
            token_url = self.cfg.get("url") + "/oauth2/tokenP"
            api_key = self.cfg.get("api_key")
            api_secret_key = self.cfg.get("api_secret_key")

        payload = {
            "grant_type": "client_credentials",
            "appkey": api_key,
            "appsecret": api_secret_key
        }

        try:
            response = requests.post(token_url, json=payload)
            if response.status_code != 200:
                logger.error(f"❌ 토큰 발급 실패: {response.status_code} {response.text}")
                raise Exception(f"토큰 갱신 실패: {response.status_code} {response.text}")

            data = response.json()
            if "access_token" not in data:
                logger.error(f"❌ access_token 누락: {data}")
                raise Exception(f"토큰 갱신 실패: access_token 누락")

            # 토큰 및 발급시간 갱신
            self.access_token = "Bearer " + data["access_token"]
            self.token_issued_at = int(time.time())

            # 헤더 갱신
            self.base_headers["authorization"] = self.access_token

            # cfg에도 갱신된 토큰과 시간 저장
            if self.is_paper_trading:
                self.cfg["papertoken"] = self.access_token
                self.cfg["papertoken_issued_at"] = self.token_issued_at
            else:
                self.cfg["realtoken"] = self.access_token
                self.cfg["realtoken_issued_at"] = self.token_issued_at

            # cfg에도 갱신된 토큰과 시간 저장 후 settings.json 저장
            # 제외할 키 목록을 명시적으로 정의
            try:
                # 1. 기존 settings.json 불러오기
                if os.path.exists(SETTINGS_FILE):
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        existing_cfg = json.load(f)
                else:
                    existing_cfg = {}

                # 2. 변한 키만 필터링해서 추출 (.env 키 제외)
                changed_cfg = {k: v for k, v in self.cfg.items() if k not in self.get_env_keys_list()}

                # 3. 기존 값에 덮어쓰기
                existing_cfg.update(changed_cfg)

                # 4. 다시 저장
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing_cfg, f, ensure_ascii=False, indent=2)

                logger.debug(f"✅ settings.json 부분 저장 완료: {SETTINGS_FILE}")

            except Exception as e:
                logger.error(f"❌ settings.json 저장 실패: {e}")

            if DEBUG:
                logger.info("✅ 토큰 갱신 완료")

        except Exception as e:
            logger.error(f"❌ 토큰 갱신 중 예외 발생: {e}")
            raise

class KoreaInvestAPI:
    def __init__(self):
        env_instance = KoreaInvestEnv() #KoreaInvestEnv의 cfg를 인스턴스로 가지고 오기
        self.cfg = env_instance.cfg
        self.access_token = env_instance.access_token
        self.base_headers = env_instance.base_headers
        self.is_paper_trading = env_instance.is_paper_trading
        self.request_base_url = env_instance.request_base_url
        self.account_num = env_instance.account_num
        self.websocket_url = self.cfg["paper_websocket_url"] if self.is_paper_trading else self.cfg["websocket_url"]
        self.approval_key = self.cfg["websocket_approval_key"]
        self.custtype = self.cfg["custtype"]
        self.htsid = self.cfg.get("htsid")

        # API의 컬럼들을 elements_map_type.json에 따라 맵핑하기 위해 로드 (label, dtype 모두)
        try:
            with open(os.path.join(CACHE_DIR, "elements_map_type.json"), "r", encoding="utf-8") as f:
                self.col_type_map = json.load(f)
            self.col_map = {k: v["label"] for k, v in self.col_type_map.items()}
        except Exception as e:
            logger.warning(f"⚠️ 컬럼 타입 매핑 파일 로딩 실패: {e}")
            self.col_type_map = {}
            self.col_map = {}
        self.col_reverse_map = {v: k for k, v in self.col_map.items()}
        self.col_order = list(self.col_map.keys())

    def set_order_hash_key(self, h, p):
        # 주문 API에서 사용할 hash key값을 받아 header에 설정해 주는 함수
        # Input: HTTP Header, HTTP post param
        # Output: None

        url = f"{self.request_base_url}/uapi/hashkey"

        res = requests.post(url, data=json.dumps(p), headers=h)
        rescode = res.status_code

        if rescode == 200:
            h["hashkey"] = res.json()["HASH"]
        else:
            if DEBUG: logger.info(f"Error: {rescode}")

    def get_and_parse_response(self, url: str, tr_id: str, params: dict, is_post_request=False, use_hash=True):
        try:
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": self.cfg["papertoken"] if self.is_paper_trading else self.cfg["realtoken"],
                "appkey": self.cfg["paper_api_key"] if self.is_paper_trading else self.cfg["api_key"],
                "appsecret": self.cfg["paper_api_secret_key"] if self.is_paper_trading else self.cfg["api_secret_key"],
                "tr_id": tr_id,
                "custtype": self.custtype,
            }

            if is_post_request:
                if use_hash:
                    self.set_order_hash_key(headers, params)
                response = requests.post(url, headers=headers, json=params)
            else:
                response = requests.get(url, headers=headers, params=params)

            if response.status_code == 200:
                if DEBUG: logger.info(f"Message : {response.status_code} | {response.text}")
                return APIResponse(response)
            else:
                if DEBUG: logger.info(f"Error Code : {response.status_code} | {response.text}")
                if DEBUG: logger.debug(f"❌ 응답 실패 본문: {response.text}")
                return None

        except Exception as e:
            logger.exception(f"❌ requests 예외 발생: {e}")
            if DEBUG: logger.debug(f"❌ 예외 발생 중 URL: {url}")
            return None

    def map_and_order_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        # 컬럼 이름 변경
        new_columns = [self.col_map.get(col, col) for col in df.columns]
        df.columns = new_columns

        # dtype 변환 수행
        for col in df.columns:
            col_key = self.col_reverse_map.get(col, col)
            dtype_info = self.col_type_map.get(col_key)
            if dtype_info:
                dtype = dtype_info.get("dtype", "str")
                try:
                    if dtype == "int":
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                    elif dtype == "float":
                        df[col] = pd.to_numeric(df[col], errors='coerce').astype(float)
                    elif dtype == "str":
                        df[col] = df[col].astype(str)
                except Exception as e:
                    logger.warning(f"⚠️ {col} 컬럼 변환 실패: {e}")
        logger.debug(f"🧾 변환된 컬럼 목록: {list(df.columns)}")
        return df

    def do_sell(self, stock_code, order_qty, order_price, order_type):
        url = self.request_base_url + "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = "VTTC0011U" if self.is_paper_trading else "TTTC0011U"

        params = {
            "CANO": self.account_num[:8],  # 종합계좌번호
            "ACNT_PRDT_CD": self.account_num[8:],  # 상품유형코드
            "PDNO": stock_code,  # 종목코드(6자리) , ETN의 경우 7자리 입력
            "SLL_TYPE": "",  # 01@일반매도 | 02@임의매매 | 05@대차매도 | → 미입력시 01 일반매도로 진행
            "ORD_DVSN": order_type,
            # [KRX] 00 : 지정가 | 01 : 시장가 | 02 : 조건부지정가 | 03 : 최유리지정가 | 04 : 최우선지정가 | 05 : 장전 시간외 | 06 : 장후 시간외 | 07 : 시간외 단일가
            # 11 : IOC지정가 (즉시체결,잔량취소) | 12 : FOK지정가 (즉시체결,전량취소) | 13 : IOC시장가 (즉시체결,잔량취소) | 14 : FOK시장가 (즉시체결,전량취소) | 15 : IOC최유리 (즉시체결,잔량취소) | 16 : FOK최유리 (즉시체결,전량취소)
            # 21 : 중간가 | 22 : 스톱지정가 | 23 : 중간가IOC | 24 : 중간가FOK
            "ORD_QTY": order_qty,  # 주문수량
            "ORD_UNPR": order_price,  # 주문단가 | 시장가 등 주문시, "0"으로 입력
            "CNDT_PRIC": "",  # 스탑지정가호가 주문 (ORD_DVSN이 22) 사용 시에만 필수
            "EXCG_ID_DVSN_CD": "KRX"
            # 한국거래소 : KRX | 대체거래소 (넥스트레이드) : NXT | SOR (Smart Order Routing) : SOR | → 미입력시 KRX로 진행되며, 모의투자는 KRX만 가능
        }

        data = self.get_and_parse_response(url, tr_id, params, is_post_request=True, use_hash=True)
        if not data:
            return pd.DataFrame()

        body = data.get_body()
        df = pd.DataFrame([body._asdict()])
        df = self.map_and_order_columns(df)

        return df

    def do_buy(self, stock_code, order_qty, order_price, order_type):
        url = self.request_base_url + "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = "VTTC0012U" if self.is_paper_trading else "TTTC0012U"

        params = {
            "CANO": self.account_num[:8],  # 종합계좌번호
            "ACNT_PRDT_CD": self.account_num[8:],  # 상품유형코드
            "PDNO": stock_code,  # 종목코드(6자리) , ETN의 경우 7자리 입력
            "SLL_TYPE": "",  # 01@일반매도 | 02@임의매매 | 05@대차매도 | → 미입력시 01 일반매도로 진행
            "ORD_DVSN": order_type, # [KRX] 00 : 지정가 | 01 : 시장가 | 02 : 조건부지정가 | 03 : 최유리지정가 | 04 : 최우선지정가 | 05 : 장전 시간외 | 06 : 장후 시간외 | 07 : 시간외 단일가
                                    # 11 : IOC지정가 (즉시체결,잔량취소) | 12 : FOK지정가 (즉시체결,전량취소) | 13 : IOC시장가 (즉시체결,잔량취소) | 14 : FOK시장가 (즉시체결,전량취소) | 15 : IOC최유리 (즉시체결,잔량취소) | 16 : FOK최유리 (즉시체결,전량취소)
                                    # 21 : 중간가 | 22 : 스톱지정가 | 23 : 중간가IOC | 24 : 중간가FOK
            "ORD_QTY": order_qty,  # 주문수량
            "ORD_UNPR": order_price,  # 주문단가 | 시장가 등 주문시, "0"으로 입력
            "CNDT_PRIC": "",  # 스탑지정가호가 주문 (ORD_DVSN이 22) 사용 시에만 필수
            "EXCG_ID_DVSN_CD": "KRX" # 한국거래소 : KRX | 대체거래소 (넥스트레이드) : NXT | SOR (Smart Order Routing) : SOR | → 미입력시 KRX로 진행되며, 모의투자는 KRX만 가능
        }

        data = self.get_and_parse_response(url, tr_id, params, is_post_request=True, use_hash=True)
        if not data:
            return pd.DataFrame()

        body = data.get_body()
        df = pd.DataFrame([body._asdict()])
        df = self.map_and_order_columns(df)

        return df

    def order_revise(self, order_branch, order_num, reve_cncl_code, qty_all, order_qty, order_price, order_type):
        # 주식주문(정정취소) 정정은 원주문에 대한 주문단가 혹은 주문구분을 변경하는 사항으로, 정정이 가능한 수량은 원주문수량을 초과 할 수 없습니다.
        # 주식주문(정정취소) 호출 전에 반드시 주식정정취소가능주문조회 호출을 통해 정정취소가능수량(output > psbl_qty)을 확인하신 후 정정취소주문 내시기 바랍니다.

        url = self.request_base_url + "/uapi/domestic-stock/v1/trading/order-rvsecncl"
        tr_id = "VTTC0013U" if self.is_paper_trading else "TTTC0013U"

        params = {
            "CANO": self.account_num[:8],
            "ACNT_PRDT_CD": self.account_num[8:],
            "KRX_FWDG_ORD_ORGNO": order_branch,
            "ORGN_ODNO": order_num,  # 종목코드(6자리) , ETN의 경우 7자리 입력
            "ORD_DVSN": order_type, # [KRX] 00 : 지정가 | 01 : 시장가 | 02 : 조건부지정가 | 03 : 최유리지정가 | 04 : 최우선지정가 | 05 : 장전 시간외 | 06 : 장후 시간외 | 07 : 시간외 단일가
                                    # 11 : IOC지정가 (즉시체결,잔량취소) | 12 : FOK지정가 (즉시체결,전량취소) | 13 : IOC시장가 (즉시체결,잔량취소) | 14 : FOK시장가 (즉시체결,전량취소) | 15 : IOC최유리 (즉시체결,잔량취소) | 16 : FOK최유리 (즉시체결,전량취소)
                                    # 21 : 중간가 | 22 : 스톱지정가 | 23 : 중간가IOC | 24 : 중간가FOK
            "RVSE_CNCL_DVSN_CD" : reve_cncl_code, # 01@정정 |02@취소
            "ORD_QTY": order_qty,  # 주문수량
            "ORD_UNPR": order_price,  # 주문단가 | 시장가 등 주문시, "0"으로 입력
            "QTY_ALL_ORD_YN": qty_all,  # 'Y@전량 | N@일부'
        }

        data = self.get_and_parse_response(url, tr_id, params, is_post_request=True, use_hash=True)
        if not data:
            return pd.DataFrame()

        body = data.get_body()
        df = pd.DataFrame([body._asdict()])
        df = self.map_and_order_columns(df)

        return df

    def current_price(self, stock_no):

        url = self.request_base_url + "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_no
        }

        data = self.get_and_parse_response(url, tr_id, params)

        if not data:
            return pd.DataFrame()
        output = data.get_body().output
        df = pd.DataFrame([output]) if isinstance(output, dict) else pd.DataFrame(output)
        df = self.map_and_order_columns(df)

        return df

    def inquire_psbl_rvsecncl(self):
        # 주식정정취소가능주문조회
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None

        url = self.request_base_url + "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        tr_id = "TTTC0084R"

        params = {
            "CANO": self.account_num[:8],
            "ACNT_PRDT_CD": self.account_num[8:],
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0",
        }

        data = self.get_and_parse_response(url, tr_id, params)

        if not data:
            return pd.DataFrame()
        output = data.get_body().output
        df = pd.DataFrame([output]) if isinstance(output, dict) else pd.DataFrame(output)
        df = self.map_and_order_columns(df)

        return df

    def inquire_psbl_order(self, stock_code, order_price, ord_dvsn):
        # 매수가능조회
        '''
        1) 매수가능금액 확인
        . 미수 사용 X: nrcvb_buy_amt(미수없는매수금액) 확인
        . 미수 사용 O: max_buy_amt(최대매수금액) 확인


        2) 매수가능수량 확인
        . 특정 종목 전량매수 시 가능수량을 확인하실 경우 ORD_DVSN:00(지정가)는 종목증거금율이 반영되지 않습니다.
        따라서 "반드시" ORD_DVSN:01(시장가)로 지정하여 종목증거금율이 반영된 가능수량을 확인하시기 바랍니다.
        (다만, 조건부지정가 등 특정 주문구분(ex.IOC)으로 주문 시 가능수량을 확인할 경우 주문 시와 동일한 주문구분(ex.IOC) 입력하여 가능수량 확인)

        . 미수 사용 X: ORD_DVSN:01(시장가) or 특정 주문구분(ex.IOC)로 지정하여 nrcvb_buy_qty(미수없는매수수량) 확인
        . 미수 사용 O: ORD_DVSN:01(시장가) or 특정 주문구분(ex.IOC)로 지정하여 max_buy_qty(최대매수수량) 확인
        '''
        url = self.request_base_url + "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        tr_id = "VTTC8908R" if self.is_paper_trading else "TTTC8908R"

        params = {
            "CANO": self.account_num[:8],  # 종합계좌번호
            "ACNT_PRDT_CD": self.account_num[8:],  # 상품유형코드
            "PDNO": stock_code,
            "ORD_UNPR": order_price, #1주당 가격 | 시장가(ORD_DVSN:01)로 조회 시, 공란으로 입력 | PDNO, ORD_UNPR 공란 입력 시, 매수수량 없이 매수금액만 조회됨
            "ORD_DVSN": ord_dvsn, # 주문구분 00 : 지정가 | 01 : 시장가 | 02 : 조건부지정가 | 03 : 최유리지정가 | 04 : 최우선지정가
                                  # 특정 종목 전량매수 시 가능수량을 확인할 경우 00:지정가는 증거금율이 반영되지 않으므로 증거금율이 반영되는 01: 시장가로 조회
                                  # 다만, 조건부지정가 등 특정 주문구분(ex.IOC)으로 주문 시 가능수량을 확인할 경우 주문 시와 동일한 주문구분(ex.IOC) 입력하여 가능수량 확인
                                  # 종목별 매수가능수량 조회 없이 매수금액만 조회하고자 할 경우 임의값(00) 입력
            "CMA_EVLU_AMT_ICLD_YN": "N", #Y : 포함 | N : 포함하지 않음
            "OVRS_ICLD_YN": "N", #Y : 포함 | N : 포함하지 않음
        }

        data = self.get_and_parse_response(url, tr_id, params)

        if not data:
            return pd.DataFrame()
        output = data.get_body().output
        df = pd.DataFrame([output]) if isinstance(output, dict) else pd.DataFrame(output)
        df = self.map_and_order_columns(df)

        return df

    def inquire_balance(self):
        # 주식잔고조회
        url = self.request_base_url + "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.is_paper_trading else "TTTC8434R"

        params = {
            "CANO": self.account_num[:8],  # 종합계좌번호
            "ACNT_PRDT_CD": self.account_num[8:],  # 상품유형코드
            "AFHR_FLPR_YN": "N",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "OFL_YN": "N",
            "INQR_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        data = self.get_and_parse_response(url, tr_id, params)
        if not data:
            return pd.DataFrame(), pd.DataFrame()

        body = data.get_body()

        # 각 output 필드를 안전하게 추출
        output1 = getattr(body, "output1", [])
        output2 = getattr(body, "output2", [])

        # 데이터프레임 변환
        df1 = pd.DataFrame(output1)
        df2 = pd.DataFrame(output2)

        df1 = self.map_and_order_columns(df1)
        df2 = self.map_and_order_columns(df2)

        return df1, df2

    def get_send_data(self, cmd=None, stock_code=None):
        # 1. 주식호가, 2.주식호가해제, 3.주식체결, 4.주식체결해제, 5.주식체결통보(고객), 6.주식체결통보해제(고객), 7.주식체결통보(모의), 8.주식체결통보해제(모의)
        # 입력값 체크 step
        logger.debug(f"websocket_approval_key: {self.approval_key}")

        assert 0 < cmd < 9, f"Wrong Input Data: {cmd}"

        #입력값에 따라 전송 데이터셋 구분 처리
        if cmd == 1: # 주식 호가 등록
            tr_id = 'H0STASP0'
            tr_type = '1'
        elif cmd == 2: # 주식호가 등록해제
            tr_id = 'H0STASP0'
            tr_type = '2'
        elif cmd == 3:  # 주식체결 등록
            tr_id = 'H0STCNT0'
            tr_type = '1'
        elif cmd == 4:  # 주식체결 등록해제
            tr_id = 'H0STCNT0'
            tr_type = '2'
        elif cmd == 5:  # 주식체결통보 등록(고객용)
            tr_id = 'H0STCNI0' #고객체결통보
            tr_type = '1'
        elif cmd == 6:  # 주식체결통보 등록해제(고객용)
            tr_id = 'H0STCNI0'  # 고객체결통보
            tr_type = '2'
        elif cmd == 7:  # 주식체결통보 등록(모의)
            tr_id = 'H0STCNI9'  # 테스트용 직원체결통보
            tr_type = '1'
        elif cmd == 8:  # 주식체결통보 등록해제(모의)
            tr_id = 'H0STCNI9'  # 테스트용 직원체결통보
            tr_type = '2'

        # send json, 체결통보는 tr_key 입력항목이 상이하므로 분리를 한다.
        if cmd in (5, 6, 7, 8):
            senddata = (
                '{"header":{"approval_key":"' + self.approval_key +
                '","custtype":"' + self.custtype +
                '","tr_type":"' + tr_type +
                '","content-type":"utf-8"},'
                '"body":{"input":{"tr_id":"' + tr_id +
                '","tr_key":"' + self.htsid + '"}}}'
            )
        else:
            senddata = (
                '{"header":{"approval_key":"' + self.approval_key +
                '","custtype":"' + self.custtype +
                '","tr_type":"' + tr_type +
                '","content-type":"utf-8"},'
                '"body":{"input":{"tr_id":"' + tr_id +
                '","tr_key":"' + stock_code + '"}}}'
            )
        return senddata

    def summarize_foreign_institution_estimates(self, stock_code):
        # 종목별 외인기관 추정가집계
        # 한국투자 MTS > 국내 현재가 > 투자자 > 투자자동향 탭 > 왼쪽구분을 '추정(주)'로 선택 시 확인 가능한 데이터
        # 입력시간은 외국인 09:30, 11:20, 13:20, 14:30 / 기관종합 10:00, 11:20, 13:20, 14:30
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None

        url = self.request_base_url + "/uapi/domestic-stock/v1/quotations/investor-trend-estimate"
        tr_id = "HHPTJ04160200"

        params = {
            "MKSC_SHRN_ISCD": stock_code
        }

        data = self.get_and_parse_response(url, tr_id, params)
        if not data:
            return pd.DataFrame(), pd.DataFrame()

        body = data.get_body()
        output2 = getattr(body, "output2", [])
        # 데이터프레임 변환
        df2 = pd.DataFrame(output2)
        df2 = self.map_and_order_columns(df2)

        return df2

    def current_price_and_investor(self, stock_code):
        # 주식현재가 투자자 | 개인, 외국인, 기관 등 투자 정보를 확인할 수 있습니다.
        url = self.request_base_url + "/uapi/domestic-stock/v1/quotations/inquire-investor"
        tr_id = "FHKST01010900" if self.is_paper_trading else "FHKST01010900"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }

        data = self.get_and_parse_response(url, tr_id, params)

        if not data:
            return pd.DataFrame(), pd.DataFrame()

        body = data.get_body()
        output = getattr(body, "output", [])
        # 데이터프레임 변환
        df = pd.DataFrame(output)
        df = self.map_and_order_columns(df)

        return df

    def foreign_net_trading_summary(self, market):
        # 외국계 매매 종목 정보를 조회하는 함수
        # 종목별이 아니라, 각 시장의 상위 종목들을 일괄로 반환
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None

        url = self.request_base_url + "/uapi/domestic-stock/v1/quotations/frgnmem-trade-estimate"
        tr_id = "FHKST644100C0"

        params = {
            "FID_COND_MRKT_DIV_CODE": 'J',  # 조건시장분류코드
            "FID_COND_SCR_DIV_CODE": "16441",  # 조건화면분류코드
            "FID_INPUT_ISCD": market,  # 입력종목코드
            "FID_RANK_SORT_CLS_CODE": "0",  # 금액순 정렬
            "FID_RANK_SORT_CLS_CODE_2": "0"  # 매수순 정렬
        }

        data = self.get_and_parse_response(url, tr_id, params)

        if not data:
            return pd.DataFrame(), pd.DataFrame()

        body = data.get_body()
        output = getattr(body, "output", [])
        # 데이터프레임 변환
        df = pd.DataFrame(output)
        df = self.map_and_order_columns(df)

        return df

    def program_trade_summary_by_time(self, stock_code, market):
        # 프로그램매매 종합현황(시간)을 종목별로 검색 요청하는 함수
        # 없는 서비스 코드라는 답변이 나옴
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None

        url = self.request_base_url + "/uapi/domestic-stock/v1/quotations/comp-program-trade-today"
        tr_id = "HPPG04600101"

        params = {
            "FID_COND_MRKT_DIV_CODE": market,  # KRX : J , NXT : NX, 통합 : UN
            "FID_INPUT_ISCD": stock_code,  # 조건화면분류코드
            "FID_INPUT_DATE_1": "",  # 입력 날짜1: 기준일 (ex 0020240308), 미입력시 당일부터 조회
        }

        data = self.get_and_parse_response(url, tr_id, params)

        if not data:
            return pd.DataFrame(), pd.DataFrame()

        body = data.get_body()
        output = getattr(body, "output", [])
        # 데이터프레임 변환
        df = pd.DataFrame(output)
        df = self.map_and_order_columns(df)

        return df

    def summarize_foreign_net_estimates(self, stock_code):
        # 종목별 외국계 순매수추이 | 한국투자 HTS(eFriend Plus) > [0433] 종목별 외국계 순매수추이 화면의 기능
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None
        url = self.request_base_url + "/uapi/domestic-stock/v1/quotations/frgnmem-pchs-trend"
        tr_id = "FHKST644400C0"

        params = {
            "FID_INPUT_ISCD": stock_code, # 종목코드(ex) 005930(삼성전자))
            "FID_INPUT_ISCD_2": "99999", # 조건화면분류코드 |외국계 전체(99999)
            "FID_COND_MRKT_DIV_CODE": "J" # J (KRX만 지원)
        }

        data = self.get_and_parse_response(url, tr_id, params)

        if not data:
            return pd.DataFrame(), pd.DataFrame()

        body = data.get_body()
        output = getattr(body, "output", [])
        # 데이터프레임 변환
        df = pd.DataFrame(output)
        df = self.map_and_order_columns(df)

        return df

class APIResponse:
    def __init__(self, resp):
        self._rescode = resp.status_code
        self._resp = resp
        self._header = self._set_header()
        self._body = self._set_body()
        self._err_code = self._body.rt_cd
        self._err_message = self._body.msg1

    def get_result_code(self):
        return self._rescode

    def _set_header(self):
        fld = {x: self._resp.headers.get(x) for x in self._resp.headers.keys() if x.islower()}
        return namedtuple("header", fld.keys())(**fld)

    def _set_body(self):
        return namedtuple("body", self._resp.json().keys())(**self._resp.json())

    def get_header(self):
        return self._header

    def get_body(self):
        return self._body

    def get_response(self):
        return self._resp

    def is_ok(self):
        try:
            return self.get_body().rt_cd == "0"
        except:
            return False

    def get_error_code(self):
        return self._err_code

    def get_error_message(self):
        return self._err_message

    def print_all(self):
        if DEBUG: logger.info("<Header>")
        for x in self.get_header()._fields:
            if DEBUG: logger.info(f"\t-{x}: {getattr(self.get_header(), x)}")
        if DEBUG: logger.info("<Body>")
        for x in self.get_body()._fields:
            if DEBUG: logger.info(f"\t-{x}: {getattr(self.get_body(), x)}")

    def print_error(self):
        if DEBUG: logger.info(f"---------------------------------")
        if DEBUG: logger.info(f"Error in response: {self.get_result_code()}")
        if DEBUG: logger.info(f"{self.get_body().rt_cd}, {self.get_error_code()}, {self.get_error_message()}")
        if DEBUG: logger.info(f"---------------------------------")