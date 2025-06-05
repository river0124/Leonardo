
import copy
import json
import time
from collections import namedtuple
import pandas as pd
import requests
from loguru import logger
import os
from dotenv import load_dotenv

from settings import cfg

BASE_DIR = os.getenv('BASE_DIR', os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.getenv('CACHE_DIR', os.path.join(BASE_DIR, 'cache'))
SETTINGS_FILE = os.getenv('SETTINGS_FILE', os.path.join(CACHE_DIR, 'settings.json'))
load_dotenv(dotenv_path='.env.local')

DEBUG = cfg.get("DEBUG", "False").lower() == "true"

# 로그 경로를 현재 파일(__file__) 기준으로 안전하게 구성
LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "trading_{time:YYYY-MM-DD}.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# 로그 파일 설정
logger.add(LOG_PATH, rotation="10 MB", retention="10 days", encoding="utf-8", enqueue=True)

def create_env_api():
    with open("cache/settings.json") as f:
        cfg = json.load(f)
    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())
    return env, api

class KoreaInvestEnv:
    def __init__(self, cfg):
        self.cfg = cfg
        self.custtype = cfg.get('custtype', 'P')
        self.api_key = cfg["api_key"]
        self.api_secret_key = cfg["api_secret_key"]
        self.base_headers = {
            "content_Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User_Agent": cfg.get("my_agent", "")
        }
        # Remove file-based token logic; just set access_token from cfg
        self.is_paper_trading = cfg.get("is_paper_trading", True)

        # 1. 토큰 선택
        if self.is_paper_trading:
            self.access_token = cfg["papertoken"]
            token_issued_at = cfg.get("papertoken_issued_at", 0)
        else:
            self.access_token = cfg["realtoken"]
            token_issued_at = cfg.get("realtoken_issued_at", 0)
        self.token_issued_at = token_issued_at  # <-- Add this line

        # 2. 현재 시간과 토큰 발급 시간 차이 체크 (23시간 = 82800초)
        current_time = int(time.time())
        if current_time - token_issued_at > 82800:  # 23시간 이상 경과
            if DEBUG:
                logger.info("⌛ 토큰 발급 후 23시간 경과, refresh_access_token 호출 예정")
            self.refresh_access_token()  # 나중에 정의할 함수

        # 3. 헤더 초기 설정
        self.base_headers["authorization"] = self.access_token

        if self.is_paper_trading:
            using_url = cfg.get("paper_url", "")
            api_key = cfg.get("paper_api_key", "")
            api_secret_key = cfg.get("paper_api_secret_key", "")
            account_num = cfg.get("paper_stock_account_number", "")
        else:
            using_url = cfg.get("url", "")
            api_key = cfg.get("api_key", "")
            api_secret_key = cfg.get("api_secret_key", "")
            account_num = cfg.get("stock_account_number", "")

        self.request_base_url = cfg["paper_url"] if self.is_paper_trading else cfg["url"]
        websocket_approval_key = cfg.get("websocket_approval_key")
        if not websocket_approval_key:
            logger.warning("❗ cfg에 approval_key 없음 – 직접 발급 시도")
            websocket_approval_key = self.get_websocket_approval_key()
        self.cfg["websocket_approval_key"] = websocket_approval_key
        # No need to call get_account_access_token (file-based); use access_token from cfg
        self.base_headers["authorization"] = self.access_token
        # Debug: show which token file is selected
        # (already logged above)
        self.base_headers["appkey"] = api_key
        self.base_headers["appsecret"] = api_secret_key
        self.cfg["account_num"] = account_num
        self.cfg["using_url"] = using_url

    def get_base_headers(self):
        headers = self.base_headers.copy()
        # Always use the access_token from cfg (already set in self.access_token)
        headers["authorization"] = self.access_token
        return headers

    def get_full_config(self):
        return copy.deepcopy(self.cfg)

    def refresh_access_token(self):
        if DEBUG:
            logger.info("🔁 토큰 갱신 시작")
        logger.debug("🛠️ [refresh_access_token] 함수 진입 확인")

        # 토큰 발급 URL
        if self.is_paper_trading:
            token_url = self.cfg.get("paper_url", "").rstrip("/") + "/oauth2/tokenP"
            api_key = self.cfg.get("paper_api_key")
            api_secret_key = self.cfg.get("paper_api_secret_key")
        else:
            token_url = self.cfg.get("url", "").rstrip("/") + "/oauth2/tokenP"
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

            new_token = "Bearer " + data["access_token"]

            # 토큰 및 발급시간 갱신
            self.access_token = new_token
            self.token_issued_at = int(time.time())

            # 헤더 갱신
            self.base_headers["authorization"] = new_token

            # cfg에도 갱신된 토큰과 시간 저장
            if self.is_paper_trading:
                self.cfg["papertoken"] = new_token
                self.cfg["papertoken_issued_at"] = self.token_issued_at
            else:
                self.cfg["realtoken"] = new_token
                self.cfg["realtoken_issued_at"] = self.token_issued_at

            # cfg에도 갱신된 토큰과 시간 저장 후 settings.json 저장
            try:
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.cfg, f, ensure_ascii=False, indent=2)
                logger.debug(f"✅ settings.json 저장 완료: {SETTINGS_FILE}")
            except Exception as e:
                logger.error(f"❌ settings.json 저장 실패: {e}")

            if DEBUG:
                logger.info("✅ 토큰 갱신 완료")

        except Exception as e:
            logger.error(f"❌ 토큰 갱신 중 예외 발생: {e}")
            raise

    def get_websocket_approval_key(self):
        logger.debug("[get_websocket_approval_key] 🔁 함수 호출됨")
        if self.is_paper_trading:
            appkey = self.cfg["paper_api_key"]
            secretkey = self.cfg["paper_api_secret_key"]
            request_base_url = self.cfg["paper_url"]
        else:
            appkey = self.cfg["api_key"]
            secretkey = self.cfg["api_secret_key"]
            request_base_url = self.cfg["url"]

        request_url = f"{request_base_url}/oauth2/Approval"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": appkey,
            "secretkey": secretkey
        }

        logger.info(f"🔑 [get_websocket_approval_key] 최종 요청 URL: {request_url}")
        logger.info(f"🔐 [get_websocket_approval_key] appkey: {appkey}, secretkey: {secretkey}")

        res = requests.post(request_url, headers=headers, data=json.dumps(body))

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

class KoreaInvestAPI:
    def __init__(self, cfg, base_headers, websocket_approval_key=None):
        self.cfg = cfg
        self.approval_key = cfg["websocket_approval_key"]
        self.custtype = cfg.get("custtype", "P")
        self._base_headers = base_headers
        self.access_token = self._base_headers.get("authorization", "")
        self.is_paper_trading = cfg.get("is_paper_trading", True)
        self.websocket_url = cfg["paper_websocket_url"] if self.is_paper_trading else cfg["websocket_url"]
        self.using_url = self.cfg["paper_url"] if self.is_paper_trading else self.cfg["url"]
        # Remove get_websocket_approval_key from KoreaInvestAPI; rely on passed or cfg.

        self.account_num = cfg.get("account_num", "")
        self.htsid = cfg.get("htsid", "")

    def set_order_hash_key(self, h, p):
        # 주문 API에서 사용할 hash key값을 받아 header에 설정해 주는 함수
        # Input: HTTP Header, HTTP post param
        # Output: None

        url = f"{self.using_url}/uapi/hashkey"

        res = requests.post(url, data=json.dumps(p), headers=h)
        rescode = res.status_code

        if rescode == 200:
            h["hashkey"] = res.json()["HASH"]
        else:
            if DEBUG: logger.info(f"Error: {rescode}")

    def do_sell(self, stock_code, order_qty, order_price, order_type="00"):
        t1 = self.do_order(stock_code, order_qty, order_price, buy_flag=False, order_type=order_type)
        return t1

    def do_buy(self, stock_code, order_qty, order_price, order_type="00"):
        t1 = self.do_order(stock_code, order_qty, order_price, buy_flag=True, order_type=order_type)
        return t1

    def do_order(self, stock_code, order_qty, order_price, prd_code="01", buy_flag=True, order_type="00"):
        url = "/uapi/domestic-stock/v1/trading/order-cash"

        if buy_flag:
            tr_id = "TTTC0012U" #실전투자 매수
            if self.is_paper_trading:
                tr_id = "VTTC0012U" #모의투자 매수

        else:
            tr_id = "TTTC0011U"  #실전투자 매도
            if self.is_paper_trading:
                tr_id = "VTTC0011U" #모의투자 매도

        params = {
            "CANO": self.account_num,
            "ACNT_PRDT_CD": prd_code,
            "PDNO" : stock_code,
            "ORD_DVSN" : order_type,
            "ORD_QTY" : str(order_qty),
            "ORD_UNPR" : str(order_price),
            "CNDT_PRIC" : "",
            "SLL_TYPE" : "01",
            "ALGO_NO" : ""
        }

        t1 = self._url_fetch(url, tr_id, params, is_post_request=True, use_hash=True)

        if t1 is not None and t1.is_ok():
            return t1
        elif t1 is None:
            return None
        else:
            t1.print_error()
            return t1

    def do_cancel(self, order_no, order_qty, order_price="01", order_branch= "06010", prd_code="01", order_dv="00", cncl_dv= "02", qty_all_yn="Y"):
        return self._do_cancel_revise(order_no, order_branch, order_qty, order_price, prd_code, order_dv, cncl_dv, qty_all_yn)

    def do_revise(self, order_no, order_qty, order_price, order_branch= "06010", prd_code="01", order_dv="00", cncl_dv= "01", qty_all_yn="Y"):
        return self._do_cancel_revise(order_no, order_branch, order_qty, order_price, prd_code, order_dv, cncl_dv, qty_all_yn)

    def get_orders(self, prd_code="01"):
        url = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        tr_id = "TTTC0084R"
        params = {
            "CANO": self.account_num,
            "ACNT_PRDT_CD": prd_code,
            "CTX_AREA_FK100" : "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0",
        }

        t1 = self._url_fetch(url, tr_id, params)

        if t1 is not None and t1.is_ok() and t1.get_body().output:
            tdf = pd.DataFrame(t1.get_body().output)
            tdf.set_index("odno", inplace=True)
            cf1 = ["pdno", "ord_qty", "ord_unpr", "ord_tmd", "ord_gno_brno", "orgn_odno", "psbl_qty"]
            cf2 = ["종목코드", "주문수량", "주문단가", "주문시간", "주문점", "원주문번호", "주문가능수량"]
            tdf = tdf[cf1]
            ren_dict = dict(zip(cf1, cf2))

            return tdf.rename(column=ren_dict)
        else:
            return None

    def _do_cancel_revise(self, order_no, order_branch, order_qty, order_price, prd_code, order_dv, cncl_dv, qty_all_yn):
        # 특정 주문 취소 (01) / 정정 (02)
        # Input: 주문번호(get_order를 호출하여 얻은 DateFrame의 index column 값이 취소 가능한 주문번호임)
        #        주문점(통상 06010), 주문수량, 주문가격, 상품코드(01), 주문유형(00), 정정구분(취소-02, 정정-01)
        # Output: ARIPresponse object

        url = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
        tr_id = "TTTC0013U"

        params = {
            "CANO": self.account_num,
            "ACNT_PRDT_CD": prd_code,
            "KRX_FWDG_ORD_ORGNO": order_branch,
            "ORGN_ODNO" : order_no,
            "ORD_DVSN" : order_dv,
            "RVSE_CNCL_DVSN_CD" : cncl_dv, #취소(02)
            "ORD_QTY" : str(order_qty),
            "ORD_UNPR" : str(order_price),
            "QTY_ALL_ORD_YN" : qty_all_yn
        }

        t1 = self._url_fetch(url, tr_id, params=params, is_post_request=True)

        if t1 is not None and t1.is_ok():
            return t1
        elif t1 is None:
            return None
        else:
            t1.print_error()
            return None

    def _url_fetch(self, api_url, tr_id, params, is_post_request=False, use_hash=True):
        try:
            url = f"{self.using_url}{api_url}"
            headers = self._base_headers.copy()
            if tr_id[0] in ("T", "J", "C"):
                if self.is_paper_trading:
                    tr_id = "V" + tr_id[1:]
            headers["tr_id"] = tr_id
            headers["custtype"] = self.custtype
            if is_post_request:
                if use_hash:
                    self.set_order_hash_key(headers, params)
                res = requests.post(url, headers=headers, data=json.dumps(params))
            else:
                res = requests.get(url, headers=headers, params=params)

            if res.status_code == 200:
                return APIResponse(res)
            else:
                if DEBUG: logger.info(f"Error Code : {res.status_code} | {res.text}")
                logger.error(f"📡 API 응답 오류: {res.status_code}, {res.text}")
                if DEBUG: logger.debug(f"❌ 응답 실패 본문: {res.text}")
                return None
        except Exception as e:
            logger.exception(f"❌ requests 예외 발생: {e}")
            if DEBUG: logger.debug(f"❌ 예외 발생 중 URL: {api_url}")
            return None


    def get_env_config(self):
        return {
            "custtype": self.custtype,
            "websocket_approval_key": self.websocket_approval_key,
            "account_num": self.account_num,
            "is_paper_trading": self.is_paper_trading,
            "htsid": self.htsid,
            "using_url": self.using_url,
            "api_key": self._base_headers.get("appkey", ""),
            "api_secret_key": self._base_headers.get("appsecret", "")
        }

    def do_cancel_all(self, skip_codes=[]):
        tdf = self.get_orders()
        if tdf is not None:
            od_list = tdf.index.to_list()
            qty_list = tdf["주문수량"].to_list()
            price_list = tdf["주문단가"].to_list()
            branch_list = tdf["주문점"].to_list()
            codes_list = tdf["종목코드"].to_list()
            cnt = 0
            for x in od_list:
                if codes_list[cnt] in skip_codes:
                    continue
                ar = self.do_cancel(x, qty_list[cnt], price_list[cnt], branch_list[cnt])
                cnt += 1
                if ar:
                    if DEBUG: logger.info(f"get_error_code: {ar.get_error_code()}, get_error_message: {ar.get_error_message()} ")
                else:
                    if DEBUG: logger.warning("주문 취소 응답 없음")
                time.sleep(0.02)

    def get_current_price(self, stock_no):
        url = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_no
        }
        t1 = self._url_fetch(url, tr_id, params)
        if t1 and t1.is_ok():
            # 📦 필수 주가 정보 필드 추출 및 통일된 구조 생성
            data = t1.get_body().output
            # 추출할 주요 필드와 한글 설명 (Korean inline comments)
            fields_to_extract = {
                "stck_prpr": "현재가",  # 주식의 현재 거래 가격
                "w52_hgpr": "52주 최고가",  # 최근 52주간의 최고 가격
                "w52_hgpr_date": "52주 최고가 일자",  # 52주 최고가가 기록된 날짜
                "w52_lwpr": "52주 최저가",  # 최근 52주간의 최저 가격
                "w52_lwpr_date": "52주 최저가 일자",  # 52주 최저가가 기록된 날짜
                "w52_hgpr_vrss_prpr_ctrt": "52주 최고가 대비 현재가 대비",  # 현재가: "52주일 최고가 대비 현재가 대비:"
                "w52_lwpr_vrss_prpr_ctrt": "52주 최저가 대비 현재가 대비",  # 현재가: "52주일 최저가 대비 현재가 대비:"
                "acml_vol": "누적거래량",  # 당일 총 거래량
                "stck_oprc": "시가",  # 당일 첫 거래 가격
                "prdy_vrss": "전일대비",  # 전일 종가 대비 절대 변화량
                "prdy_vrss_sign": "전일대비부호",  # 전일 대비 상승/하락/보합 부호
                "prdy_ctrt": "전일 대비율",  # 전일 종가 대비 등락률(%)
                "stck_hgpr": "주식 최고가",  # 당일 최고 가격
                "stck_lwpr": "주식 최저가",  # 당일 최저 가격
                "stck_mxpr": "주식 상한가",  # 상한가 제한 가격
                "stck_llam": "주식 하한가",  # 하한가 제한 가격
                "stck_sdpr": "주식 기준가",  # 기준 가격 (보통 전일 종가)
                "d250_hgpr": "250일 최고가",  # 최근 250일 간 최고가
                "d250_hgpr_date": "250일 최고가 일자",  # 250일 최고가 기록일
                "d250_hgpr_vrss_prpr_rate": "250일 최고가 대비 현재가 비율",  # 현재가가 250일 최고가 대비 몇 %인지
                "d250_lwpr": "250일 최저가",  # 최근 250일 간 최저가
                "d250_lwpr_date": "250일 최저가 일자",  # 250일 최저가 기록일
                "d250_lwpr_vrss_prpr_rate": "250일 최저가 대비 현재가 비율",  # 현재가가 250일 최저가 대비 몇 %인지
            }
            stock_info = {k: data.get(k) for k in fields_to_extract}
            # 기존의 52주/250일 대비율 필드(혹시 추가 필드 필요시 아래처럼 유지)
            stock_info["w52_hgpr_vrss_prpr_ctrt"] = data.get("w52_hgpr_vrss_prpr_ctrt")
            stock_info["w52_lwpr_vrss_prpr_ctrt"] = data.get("w52_lwpr_vrss_prpr_ctrt")
            return stock_info
        elif t1 is None:
            return dict()
        else:
            t1.print_error()
            return dict()

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
        elif cmd == 5:  # 주실체결통보 등록(고객용)
            tr_id = 'H0STCNI0' #고객체결통보
            tr_type = '1'
        elif cmd == 6:  # 주실체결통보 등록해제(고객용)
            tr_id = 'H0STCNI0'  # 고객체결통보
            tr_type = '2'
        elif cmd == 7:  # 주실체결통보 등록(모의)
            tr_id = 'H0STCNI9'  # 테스트용 직원체결통보
            tr_type = '1'
        elif cmd == 8:  # 주실체결통보 등록해제(모의)
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


    def get_holdings_detailed(self):
        url = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.is_paper_trading else "TTTC8434R"
        params = {
            "CANO": self.account_num[:8],
            "ACNT_PRDT_CD": self.account_num[8:],
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

        response = self._url_fetch(url, tr_id, params)
        if DEBUG: logger.debug(f"📦 holdings_detailed API 응답 전체: {response.get_response().text if response else '응답 없음'}")
        if response is None or not response.is_ok():
            if DEBUG: logger.warning("❌ API 호출 실패 또는 응답 오류")
            return None

        body = response.get_body()
        output1 = pd.DataFrame(body.output1) if hasattr(body, "output1") else pd.DataFrame()

        # Robust extraction of output2
        output2 = {}
        if hasattr(body, "output2") and isinstance(body.output2, list) and body.output2:
            output2 = body.output2[0]
        else:
            if DEBUG: logger.warning("⚠️ output2 비어 있음 — 총자산 요약 불가")

        summary = {
            "예수금총금액": output2.get("dnca_tot_amt"),
            "익일정산금액": output2.get("nxdy_excc_amt"),
            "가수도정산금액": output2.get("prvs_rcdl_excc_amt"),
            "총평가금액": output2.get("tot_evlu_amt"),
            "자산증감액": output2.get("asst_icdc_amt"),
            "금일매수수량": output2.get("thdt_buyqty"),
            "금일매도수량": output2.get("thdt_sll_qty"),
            "금일제비용금액": output2.get("thdt_tlex_amt")
        }

        if DEBUG: logger.debug(f"📊 output1 (보유 종목): {output1}")
        if DEBUG: logger.debug(f"📈 summary (총자산 요약): {summary}")

        # Check for empty holdings (output1)
        if output1.empty:
            if DEBUG: logger.debug("📭 보유 종목 없음: output1이 비어 있음")
            return {
                "stocks": [],
                "summary": summary,
                "is_empty": True
            }

        return {
            "stocks": output1.to_dict(orient='records'),
            "summary": summary,
            "is_empty": False
        }

    def get_candle_data(self, stock_code):
        from get_candle_data import get_candle_chart_data
        return get_candle_chart_data(stock_code)


    def get_total_asset(self):
        url = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.is_paper_trading else "TTTC8434R"
        params = {
            "CANO": self.account_num[:8],
            "ACNT_PRDT_CD": self.account_num[8:],
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

        response = self._url_fetch(url, tr_id, params)

        if response and response.is_ok():
            body = response.get_body()
            try:
                if hasattr(body, "output2") and body.output2:
                    return int(body.output2[0]["tot_evlu_amt"])
                else:
                    return None
            except Exception as e:
                if DEBUG: logger.info(f"총자산 추출 오류: {e}")
                return None

    def refresh_access_token(self):
        if DEBUG:
            logger.info("🔁 토큰 갱신 시작")
            logger.debug("🛠️ [refresh_access_token] 함수 진입 확인")

        token_url = (self.cfg.get("paper_url") if self.is_paper_trading else self.cfg.get("url")).rstrip("/") + "/oauth2/tokenP"
        api_key = self.cfg.get("paper_api_key") if self.is_paper_trading else self.cfg.get("api_key")
        api_secret_key = self.cfg.get("paper_api_secret_key") if self.is_paper_trading else self.cfg.get("api_secret_key")

        payload = {
            "grant_type": "client_credentials",
            "appkey": api_key,
            "appsecret": api_secret_key
        }

        try:
            response = requests.post(token_url, json=payload)
            if response.status_code != 200:
                raise Exception(f"토큰 갱신 실패: {response.status_code} {response.text}")

            data = response.json()
            new_token = "Bearer " + data.get("access_token", "")
            if not new_token.strip():
                raise Exception(f"토큰 갱신 실패: access_token 누락 - {data}")

            self.access_token = new_token
            self.token_issued_at = int(time.time())
            self.base_headers["authorization"] = new_token

            if self.is_paper_trading:
                self.cfg["papertoken"] = new_token
                self.cfg["papertoken_issued_at"] = self.token_issued_at
            else:
                self.cfg["realtoken"] = new_token
                self.cfg["realtoken_issued_at"] = self.token_issued_at

            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            if DEBUG:
                logger.debug(f"✅ settings.json 저장 완료: {SETTINGS_FILE}")
                logger.debug(f"🧾 저장된 cfg 내용: {json.dumps(self.cfg, ensure_ascii=False, indent=2)}")

            # 다시 로드
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self.cfg = json.load(f)
                self.token_issued_at = (
                    self.cfg.get("papertoken_issued_at") if self.is_paper_trading
                    else self.cfg.get("realtoken_issued_at")
                )
                if DEBUG:
                    logger.debug(f"🧾 다시 로드된 token_issued_at: {self.token_issued_at}")
            except Exception as e:
                logger.error(f"❌ settings.json 다시 로드 실패: {e}")

            if DEBUG:
                logger.info("✅ 토큰 갱신 완료")

        except Exception as e:
            logger.error(f"❌ 토큰 갱신 중 예외 발생: {e}")
            raise

    def summarize_foreign_institution_estimates(self, stock_code):
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None

        url = self.using_url + "/uapi/domestic-stock/v1/quotations/investor-trend-estimate"
        tr_id = "HHPTJ04160200"

        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": self.cfg["realtoken"],
            "appkey": self.cfg["api_key"],
            "appsecret": self.cfg["api_secret_key"],
            "tr_id": tr_id,
            "custtype": "P",
        }
        params = {
            "MKSC_SHRN_ISCD": stock_code
        }

        response = requests.get(url, headers=headers, params=params)

        return response


    def get_foreign_net_trading_summary(self, market):
        # 외국계 매매 종목 정보를 조회하는 함수
        # 종목별이 아니라, 각 시장의 상위 종목들을 일괄로 반환
        if DEBUG:
            logger.info("🔁 외국계 매매종목 가집계 시작")
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None

        url = self.using_url + "/uapi/domestic-stock/v1/quotations/frgnmem-trade-estimate"
        tr_id = "FHKST644100C0"

        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": self.access_token,
            "appkey": self.cfg["api_key"],
            "appsecret": self.cfg["api_secret_key"],
            "custtype": "P",
            "tr_id": tr_id
        }

        # 📌 frgnmem-trade-estimate API 호출 파라미터 설명 (출처: 한국투자증권 OpenAPI 문서)
        # - FID_COND_MRKT_DIV_CODE: 조건시장분류코드 ("J" = 코스피, "K" = 코스닥 등)
        # - FID_COND_SCR_DIV_CODE: 조건화면분류코드 (일반적으로 빈 문자열)
        # - FID_INPUT_ISCD: 입력종목코드 (예: "005930" = 삼성전자)
        # - FID_RANK_SORT_CLS_CODE: 정렬 기준 1 ("0" = 기본, "1" = 금액순 등)
        # - FID_RANK_SORT_CLS_CODE_2: 정렬 기준 2 ("0" = 기본, "1" = 매수순 등)

        params = {
            "FID_COND_MRKT_DIV_CODE": 'J',  # 조건시장분류코드
            "FID_COND_SCR_DIV_CODE": "16441",  # 조건화면분류코드
            "FID_INPUT_ISCD": market,   # 입력종목코드
            "FID_RANK_SORT_CLS_CODE": "0",  # 금액순 정렬
            "FID_RANK_SORT_CLS_CODE_2": "0" # 매수순 정렬
        }

        response = requests.get(url, headers=headers, params=params)

        if DEBUG:
            logger.debug(f"📄 응답 원문 (text):\n{response.text}")
            logger.debug(f"🌐 HTTP 응답 코드: {response.status_code}")
        try:
            response_json = response.json()
            if DEBUG:
                logger.debug(f"📦 응답 JSON keys: {list(response_json.keys())}")
            output = pd.DataFrame(response_json.get("output", []))
        except Exception as e:
            logger.warning(f"❌ 응답 JSON 파싱 실패: {e}")
            output = pd.DataFrame()

        # 주요 컬럼 정보 주석
        # "stck_shrn_iscd" | 주식단축종목코드
        # "hts_kor_isnm" | HTS한글종목명
        # "orgn_fake_ntby_qty" | 기관순매수수량
        # "glob_ntsl_qty" | 외국계순매도수량
        # "stck_prpr" | 주식현재가
        # "prdy_vrss" | 전일대비
        # "prdy_vrss_sign" | 전일대비부호
        # "prdy_ctrt" | 전일대비율
        # "acml_vol" | 누적거래량
        # "glob_total_seln_qty" | 외국계총매도수량
        # "glob_total_shnu_qty" | 외국계총매수수량

        return output

    def get_program_trade_summary_by_time(self, stock_code, market):
        # 프로그램매매 종합현황(시간)을 종목별로 검색 요청하는 함수
        if DEBUG:
            logger.info("🔁 프로그램매매 종합현황 시작")
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None

        url = self.using_url + "/uapi/domestic-stock/v1/quotations/comp-program-trade-today"
        tr_id = "HPPG04600101"

        logger.info(url, tr_id)

        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": self.access_token,
            "appkey": self.cfg["api_key"],
            "appsecret": self.cfg["api_secret_key"],
            "tr_id": tr_id,
            "custtype": "P"
        }

        params = {
            "FID_COND_MRKT_DIV_CODE": market,  # KRX : J , NXT : NX, 통합 : UN
            "FID_INPUT_ISCD": stock_code,  # 조건화면분류코드
            "FID_INPUT_DATE_1": "",  # 입력 날짜1: 기준일 (ex 0020240308), 미입력시 당일부터 조회
        }

        response = requests.get(url, headers=headers, params=params)
        if DEBUG:
            logger.debug(f"📄 응답 원문 (text):\n{response.text}")
            logger.debug(f"🌐 HTTP 응답 코드: {response.status_code}")
        try:
            response_json = response.json()
            if DEBUG:
                logger.debug(f"📦 응답 JSON keys: {list(response_json.keys())}")
            output = pd.DataFrame(response_json.get("output", []))
        except Exception as e:
            logger.warning(f"❌ 응답 JSON 파싱 실패: {e}")
            output = pd.DataFrame()

        return output

    def summarize_foreign_net_estimates(self, stock_code):
        if self.is_paper_trading:
            logger.info("모의투자는 지원하지 않습니다.")
            return None
        url = self.using_url + "/uapi/domestic-stock/v1/quotations/frgnmem-pchs-trend"
        tr_id = "FHKST644400C0"

        headers = {
            "content-type": "application/json",
            "authorization": self.cfg["realtoken"],
            "appkey": self.cfg["api_key"],
            "appsecret": self.cfg["api_secret_key"],
            "tr_id": tr_id,
            "custtype": "P",
        }
        params = {
            "FID_INPUT_ISCD": stock_code, # 종목코드(ex) 005930(삼성전자))
            "FID_INPUT_ISCD_2": "99999", # 조건화면분류코드 |외국계 전체(99999)
            "FID_COND_MRKT_DIV_CODE": "J" # J (KRX만 지원)
        }

        response = requests.get(url, headers=headers, params=params)

        return response


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
    # (Method removed: get_order_detail)