import copy
import json
import time
import os
from collections import namedtuple

import requests
from loguru import logger


# 로그 경로를 현재 파일(__file__) 기준으로 안전하게 구성
LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "trading_{time:YYYY-MM-DD}.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# 로그 파일 설정
logger.add(LOG_PATH, rotation="10 MB", retention="10 days", encoding="utf-8", enqueue=True)
import pandas as pd

class KoreaInvestEnv:
    def __init__(self, cfg):
        self.cfg = cfg
        self.custtype = cfg.get('custtype', 'P')
        self.base_headers = {
            "content_Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User_Agent": cfg.get("my_agent", "")
        }
        # Maintain both real and paper access tokens
        self.access_token_real = None
        self.access_token_paper = None
        # Initialize self.access_token for base_headers logic
        self.access_token = None
        is_paper_trading = cfg.get("is_paper_trading", True)
        if is_paper_trading:
            using_url = cfg.get("paper_url", "")
            api_key = cfg.get("paper_api_key", "")
            api_secret_key = cfg.get("paper_api_secret_key", "")
            account_num = cfg.get("paper_stock_account_number", "")
        else:
            using_url = cfg.get("url", "")
            api_key = cfg.get("api_key", "")
            api_secret_key = cfg.get("api_secret_key", "")
            account_num = cfg.get("stock_account_number", "")
        websocket_approval_key = self.get_websocket_approval_key(using_url, api_key, api_secret_key)
        account_access_token = self.get_account_access_token(using_url, api_key, api_secret_key)
        logger.debug(f"🎫 선택된 토큰: {'token_paper.json' if is_paper_trading else 'token_real.json'}")
        self.base_headers["authorization"] = self.get_access_token()
        # Debug: show which token file is selected
        # (already logged above)
        self.base_headers["appkey"] = api_key
        self.base_headers["appsecret"] = api_secret_key
        self.cfg["websocket_approval_key"] = websocket_approval_key
        self.cfg["account_num"] = account_num
        self.cfg["using_url"] = using_url

    def get_base_headers(self):
        headers = self.base_headers.copy()
        if "authorization" not in headers or headers["authorization"] is None:
            self.access_token = self.get_access_token()
            if self.access_token is None:
                self.access_token = self.get_account_access_token(
                    self.cfg.get("paper_url") if self.cfg.get("is_paper_trading", True) else self.cfg.get("url"),
                    self.cfg.get("paper_api_key") if self.cfg.get("is_paper_trading", True) else self.cfg.get("api_key"),
                    self.cfg.get("paper_api_secret_key") if self.cfg.get("is_paper_trading", True) else self.cfg.get("api_secret_key")
                )
            logger.debug("🔑 발급된 access_token: %s", self.access_token)
            headers["authorization"] = self.access_token
        return headers

    def get_full_config(self):
        return copy.deepcopy(self.cfg)

    def get_account_access_token(self, request_base_url="", api_key="", api_secret_key=""):
        cfg = self.cfg
        token_path = os.path.join("cache", "token_paper.json") if cfg.get("is_paper_trading", True) else os.path.join("cache", "token_real.json")
        # Debug: print selected token file path
        logger.debug(f"🗂️ 토큰 저장 파일 경로: {token_path}")

        # Respect is_paper_trading and set request_base_url accordingly if not provided
        if not request_base_url:
            request_base_url = cfg.get("paper_url", "") if cfg.get("is_paper_trading", True) else cfg.get("url", "")

        # 기존 토큰이 존재하고 23시간 내면 재사용
        if os.path.exists(token_path):
            with open(token_path, "r") as f:
                token_data = json.load(f)
                if time.time() - token_data.get("timestamp", 0) < 23 * 3600:
                    logger.debug(f"♻️ 재사용 access_token from {token_path}: {token_data['token']}")
                    self.access_token = token_data["token"]
                    return token_data["token"]

        # 새로 발급
        p = {
            "grant_type": "client_credentials",
            "appkey": api_key,
            "appsecret": api_secret_key
        }
        url = f'{request_base_url}/oauth2/tokenP'
        # Use minimal headers for token request
        res = requests.post(url, data=json.dumps(p), headers={"content-type": "application/json"})
        res.raise_for_status()
        my_token = res.json()["access_token"]
        logger.debug(f"access_token: {my_token}")
        bearer_token = f"Bearer {my_token}"

        # 파일 저장
        with open(token_path, "w") as f:
            json.dump({"token": bearer_token, "timestamp": time.time()}, f)

        # Store in appropriate attribute
        if request_base_url == self.cfg.get("paper_url", ""):
            self.access_token_paper = bearer_token
        else:
            self.access_token_real = bearer_token

        # Ensure base headers are updated with the correct token
        self.base_headers["authorization"] = bearer_token
        # Debug: print stored access_token
        logger.debug(f"✅ 저장된 access_token: {bearer_token}")
        self.access_token = bearer_token

        return bearer_token

    def get_access_token(self):
        if self.cfg.get("is_paper_trading", True):
            paper_token_path = os.path.join("cache", "token_paper.json")
            if not self.access_token_paper and os.path.exists(paper_token_path):
                with open(paper_token_path, "r") as f:
                    self.access_token_paper = json.load(f)["token"]
                    logger.debug(f"📥 불러온 access_token (paper): {self.access_token_paper}")
            self.access_token = self.access_token_paper
            return self.access_token_paper
        else:
            real_token_path = os.path.join("cache", "token_real.json")
            if not self.access_token_real and os.path.exists(real_token_path):
                with open(real_token_path, "r") as f:
                    self.access_token_real = json.load(f)["token"]
                    logger.debug(f"📥 불러온 access_token (real): {self.access_token_real}")
            self.access_token = self.access_token_real
            return self.access_token_real

    def get_websocket_approval_key(self, request_base_url="", api_key="", api_secret_key=""):
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": api_key,
            "secretkey": api_secret_key
        }
        url = f'{request_base_url}/oauth2/Approval'
        res = requests.post(url, headers=headers, data=json.dumps(body))
        approval_key = res.json()["approval_key"]
        return approval_key

class KoreaInvestAPI:
    def __init__(self, cfg, base_headers):
        self.custtype = cfg.get("custtype", "P")
        self._base_headers = base_headers
        self.websocket_approval_key = cfg.get("websocket_approval_key", "")
        self.account_num = cfg.get("account_num", "")
        self.is_paper_trading = cfg.get("is_paper_trading", True)
        self.htsid = cfg.get("htsid", "")
        self.using_url = cfg.get("using_url", "")

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
            logger.info(f"Error: {rescode}")

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
        logger.debug(f"🔍 _url_fetch 진입: api_url={api_url}, tr_id={tr_id}, is_post={is_post_request}")
        try:
            url = f"{self.using_url}{api_url}"
            logger.debug(f"📡 요청 URL: {url}")
            headers = self._base_headers.copy()
            if tr_id[0] in ("T", "J", "C"):
                if self.is_paper_trading:
                    tr_id = "V" + tr_id[1:]
            headers["tr_id"] = tr_id
            headers["custtype"] = self.custtype
            logger.debug(f"📡 요청 헤더: {headers}")
            logger.debug(f"📡 요청 파라미터: {params}")

            if is_post_request:
                if use_hash:
                    self.set_order_hash_key(headers, params)
                res = requests.post(url, headers=headers, data=json.dumps(params))
            else:
                res = requests.get(url, headers=headers, params=params)

            if res.status_code == 200:
                logger.debug(f"✅ 응답 수신 완료: {res.status_code}")
                return APIResponse(res)
            else:
                logger.info(f"Error Code : {res.status_code} | {res.text}")
                logger.error(f"📡 API 응답 오류: {res.status_code}, {res.text}")
                logger.debug(f"❌ 응답 실패 본문: {res.text}")
                return None
        except Exception as e:
            logger.exception(f"❌ requests 예외 발생: {e}")
            logger.debug(f"❌ 예외 발생 중 URL: {api_url}")
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
                    logger.info(f"get_error_code: {ar.get_error_code()}, get_error_message: {ar.get_error_message()} ")
                else:
                    logger.warning("주문 취소 응답 없음")
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
            return t1.get_body().output
        elif t1 is None:
            return dict()
        else:
            t1.print_error()
            return dict()

    def get_send_data(self, cmd=None, stockcode=None):
        # 1. 주식호가, 2.주식호가해제, 3.주식체결, 4.주식체결해제, 5.주식체결통보(고객), 6.주식체결통보해제(고객), 7.주식체결통보(모의), 8.주식체결통보해제(모의)
        # 입력값 체크 step
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


        # # send json, 체결통보는 tr_key 입력항목이 상이하므로 분리를 한다.
        # if cmd in (5, 6, 7, 8):
        #     senddata = '{"header":{"approval_key":"' + self.q_approval_key + '","personalseckey":"' + self.q_personalsecKey + '","custtype":"' + self.custtype + '","tr_type":' + tr_type +

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
        logger.debug(f"📦 holdings_detailed API 응답 전체: {response.get_response().text if response else '응답 없음'}")
        if response is None or not response.is_ok():
            logger.warning("❌ API 호출 실패 또는 응답 오류")
            return None

        body = response.get_body()
        output1 = pd.DataFrame(body.output1) if hasattr(body, "output1") else pd.DataFrame()

        # Robust extraction of output2
        output2 = {}
        if hasattr(body, "output2") and isinstance(body.output2, list) and body.output2:
            output2 = body.output2[0]
        else:
            logger.warning("⚠️ output2 비어 있음 — 총자산 요약 불가")

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

        logger.debug(f"📊 output1 (보유 종목): {output1}")
        logger.debug(f"📈 summary (총자산 요약): {summary}")

        return {
            "stocks": output1,
            "summary": summary
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
                logger.info(f"총자산 추출 오류: {e}")
                return None

    def refresh_access_token(self):
        logger.info("🔁 토큰 갱신 시작")
        is_paper = self.cfg.get("is_paper_trading", True)
        api_key = self.cfg.get("paper_api_key" if is_paper else "api_key")
        api_secret_key = self.cfg.get("paper_api_secret_key" if is_paper else "api_secret_key")
        using_url = self.cfg.get("paper_url" if is_paper else "url")

        new_token = self.get_account_access_token(using_url, api_key, api_secret_key)
        self.base_headers["authorization"] = new_token
        logger.info("✅ 토큰 갱신 완료")

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
        logger.info("<Header>")
        for x in self.get_header()._fields:
            logger.info(f"\t-{x}: {getattr(self.get_header(), x)}")
        logger.info("<Body>")
        for x in self.get_body()._fields:
            logger.info(f"\t-{x}: {getattr(self.get_body(), x)}")

    def print_error(self):
        logger.info(f"---------------------------------")
        logger.info(f"Error in response: {self.get_result_code()}")
        logger.info(f"{self.get_body().rt_cd}, {self.get_error_code()}, {self.get_error_message()}")
        logger.info(f"---------------------------------")
    # (Method removed: get_order_detail)
def create_env_api():
    with open("cache/settings.json") as f:
        cfg = json.load(f)
    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())
    return env, api