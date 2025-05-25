# flask_server.py
import json
import os
import pandas as pd
from flask import Flask, request, jsonify, Response
from cryptography.fernet import Fernet
# import logging # app.logger.setLevel을 사용하려면 필요

from get_asset import get_total_asset
from get_candle_data import get_candle_chart_data
from watchlist_store import load_watchlist, add_code_to_watchlist, remove_code_from_watchlist
from utils import KoreaInvestEnv, KoreaInvestAPI
from stock_name_finder import get_stock_name_by_code

DEBUG = 0  # Set to 1 to enable print, 0 to disable

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")
STOCK_LIST_CSV = os.path.join(CACHE_DIR, "stock_list.csv")

# Fernet encryption setup
FERNET_KEY_FILE = os.path.join(CACHE_DIR, "key.secret")
if os.path.exists(FERNET_KEY_FILE):
    with open(FERNET_KEY_FILE, "rb") as f:
        FERNET_KEY = f.read()
else:
    FERNET_KEY = Fernet.generate_key()
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(FERNET_KEY_FILE, "wb") as f:
        f.write(FERNET_KEY)
fernet = Fernet(FERNET_KEY)

# Flask 앱 초기화
app = Flask(__name__)


# 로깅 레벨 설정 (선택 사항)
# if DEBUG:
#     app.logger.setLevel(logging.DEBUG)
# else:
#     app.logger.setLevel(logging.INFO)

# 설정 불러오기
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            # Decrypt sensitive fields
            for key in ["api_key", "access_token"]:
                if key in settings and isinstance(settings[key], str):
                    try:
                        settings[key] = fernet.decrypt(settings[key].encode()).decode()
                    except Exception:
                        pass  # If not decryptable, leave as is
            return settings
        except json.JSONDecodeError:
            app.logger.warning(f"Warning: Could not decode JSON from {SETTINGS_FILE}. Returning empty settings.")
            return {}
    return {}

# 설정 저장
def save_settings(settings_dict: dict):
    current_settings = load_settings()
    # Encrypt sensitive fields
    for key in ["api_key", "access_token"]:
        if key in settings_dict and isinstance(settings_dict[key], str):
            settings_dict[key] = fernet.encrypt(settings_dict[key].encode()).decode()
    current_settings.update(settings_dict)
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current_settings, f, indent=2, ensure_ascii=False)


# 초기 설정 및 API 객체 생성
cfg = load_settings()
if DEBUG:
    print("🐞 cfg loaded:", cfg)

env = KoreaInvestEnv(cfg)
api = KoreaInvestAPI(cfg=env.get_full_config(), base_headers=env.get_base_headers())

# 주식 목록 CSV 파일 로드
try:
    stock_df = pd.read_csv(STOCK_LIST_CSV, dtype=str)
except FileNotFoundError:
    app.logger.error(f"Fatal: Stock list file not found at {STOCK_LIST_CSV}. Some functionalities might not work.")
    stock_df = pd.DataFrame(columns=['Code', 'Name'])  # 빈 DataFrame으로 초기화하여 이후 코드 실행 보장
except Exception as e:
    app.logger.error(f"Fatal: Error loading stock list {STOCK_LIST_CSV}: {e}")
    stock_df = pd.DataFrame(columns=['Code', 'Name'])


@app.route('/candle', methods=['GET'])
def candle():
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Missing code parameter"}), 400

    try:
        result = get_candle_chart_data(code)  # 이 함수가 API 호출을 포함한다고 가정
        candles = result.get("candles", [])
        # open, high, low, close 값이 모두 존재하고 0 이상인 캔들만 필터링
        valid_candles = [
            c for c in candles if all(
                c.get(k) is not None and (isinstance(c.get(k), (int, float)) and c.get(k) >= 0)
                for k in ['open', 'high', 'low', 'close']
            )
        ]

        if DEBUG:
            print("🛠 필터 전 캔들 수:", len(candles))
            print("🛠 필터 후 캔들 수:", len(valid_candles))
            # 디버그 출력 시, 필터링된 결과를 포함한 최종 result를 출력하는 것이 더 유용할 수 있습니다.
            # temp_result_for_debug = result.copy()
            # temp_result_for_debug["candles"] = valid_candles
            # print(json.dumps(temp_result_for_debug, indent=2, ensure_ascii=False))

        result["candles"] = valid_candles
        return jsonify(result), 200
    except Exception as e:
        app.logger.error(f"Error in /candle for code {code}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/asset', methods=['GET'])
def asset():
    try:
        total_asset = get_total_asset()  # from get_asset import get_total_asset
        if total_asset is None:
            return jsonify({"error": "총자산을 불러올 수 없습니다."}), 500  # 또는 404
        # total_asset이 숫자형이라면 str() 변환 없이 그대로 반환하는 것이 일반적입니다.
        # 클라이언트가 문자열을 기대한다면 str(total_asset)이 맞습니다.
        return jsonify({"balance": total_asset})
    except Exception as e:
        app.logger.error(f"Error in /asset: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/high52", methods=["GET"])
def high52():
    try:
        # HIGH52_JSON_FILE = os.path.join(CACHE_DIR, "high52.json") # 변수 사용 권장
        with open(os.path.join(CACHE_DIR, "high52.json"), encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    except FileNotFoundError:
        app.logger.warning(f"/high52: high52.json not found.")
        return jsonify({"error": "52주 신고가 데이터를 찾을 수 없습니다."}), 404
    except Exception as e:
        app.logger.error(f"Error in /high52: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/price', methods=['GET'])
def get_price():
    stock_no = request.args.get('stock_no')
    if not stock_no:
        return jsonify({"error": "stock_no is required"}), 400
    try:
        data = api.get_current_price(stock_no)  # API 호출
        if not data:  # API 응답이 비어있는 경우 처리
            return jsonify({"error": f"종목 코드 {stock_no}에 대한 가격 정보를 찾을 수 없습니다."}), 404

        # stock_df에서 종목명 찾기
        if not stock_df.empty and 'Code' in stock_df.columns and 'Name' in stock_df.columns:
            names_series = stock_df.loc[stock_df['Code'] == stock_no, 'Name']
            stock_name = names_series.iloc[0] if not names_series.empty else "정보없음"
        else:
            stock_name = "정보없음 (목록 확인 필요)"
            app.logger.warning("Stock dataframe is empty or missing columns for name lookup in /price.")

        filtered_data = {
            "name": stock_name,
            "stck_prpr": data.get("stck_prpr"),  # 현재가
            "stck_oprc": data.get("stck_oprc"),  # 시가
            "stck_hgpr": data.get("stck_hgpr"),  # 고가
            "stck_lwpr": data.get("stck_lwpr"),  # 저가
            "prdy_vrss": data.get("prdy_vrss"),  # 전일 대비
            "prdy_ctrt": data.get("prdy_ctrt"),  # 전일 대비율
            "acml_vol": data.get("acml_vol"),  # 누적 거래량
            "hts_avls": data.get("hts_avls"),  # HTS 시가총액 (억) - API 응답에 따라 다를 수 있음
            "w52_hgpr": data.get("w52_hgpr"),  # 52주 최고가
            "w52_lwpr": data.get("w52_lwpr")  # 52주 최저가
        }
        return Response(
            json.dumps(filtered_data, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        app.logger.error(f"Error in /price for stock_no {stock_no}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/watchlist", methods=["GET", "POST", "DELETE"])
def watchlist():
    try:
        if request.method == "GET":
            return jsonify({"watchlist": load_watchlist()})

        data = request.get_json()
        if not data or "code" not in data:  # 데이터 존재 및 'code' 필드 확인
            return jsonify({"error": "Missing 'code' field in request body"}), 400

        code = data["code"]

        if request.method == "POST":
            add_code_to_watchlist(code)
            return jsonify({"message": f"{code} added to watchlist."}), 200  # 201 Created도 고려 가능

        if request.method == "DELETE":
            remove_code_from_watchlist(code)
            return jsonify({"message": f"{code} removed from watchlist."}), 200

    except Exception as e:
        app.logger.error(f"Error in /watchlist: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/stockname', methods=['GET'])
def stockname():
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Missing code parameter"}), 400

    # get_stock_name_by_code 함수는 stock_df를 직접 사용할 수도 있고, 별도 로직일 수도 있음
    # 여기서는 제공된 함수를 그대로 사용
    name = get_stock_name_by_code(code)
    if name:
        return jsonify({"code": code, "name": name})
    else:
        return jsonify({"error": f"Stock name not found for code {code}"}), 404


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'GET':
        try:
            return jsonify(load_settings()), 200
        except Exception as e:  # load_settings 내부에서 예외 처리하므로, 여기서는 일반적인 오류로 처리
            app.logger.error(f"Error in GET /settings: {str(e)}", exc_info=True)
            return jsonify({"error": "Failed to load settings"}), 500
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Request body is missing or not JSON"}), 400
            if DEBUG:
                print("📩 POST /settings 요청 수신:", data)

            save_settings(data)
            # 설정 변경 후 API 객체 재초기화
            global cfg, env, api
            cfg = load_settings()
            env = KoreaInvestEnv(cfg)
            api = KoreaInvestAPI(cfg=env.get_full_config(), base_headers=env.get_base_headers())
            app.logger.info("Settings updated and API re-initialized.")
            return jsonify({"message": "Settings saved successfully"}), 200
        except Exception as e:
            app.logger.error(f"Error in POST /settings: {str(e)}", exc_info=True)
            return jsonify({"error": "Failed to save settings"}), 500


@app.route('/holdings/detail', methods=['GET'])
def holdings_detail():
    try:
        result = api.get_holdings_detailed()  # API 호출
        if result is None or "stocks" not in result or "summary" not in result:
            return jsonify({"error": "보유 종목 정보를 가져올 수 없습니다."}), 404  # 또는 500

        stocks_data = result["stocks"]
        summary_data = result["summary"]

        if isinstance(stocks_data, pd.DataFrame):
            if not stocks_data.empty:
                # 'trad_dvsn_name' 컬럼이 없을 수도 있으므로 errors='ignore' 사용
                stocks_list = stocks_data.drop(columns=["trad_dvsn_name"], errors="ignore").to_dict(orient="records")
            else:
                stocks_list = []
        elif isinstance(stocks_data, list):  # 이미 list 형태일 경우 그대로 사용
            stocks_list = stocks_data
        else:
            stocks_list = []  # 예상치 못한 타입일 경우 빈 리스트로 처리

        # summary에서 특정 키 제거 (원본 summary_data를 변경하지 않도록 복사 후 작업 권장)
        # final_summary = {k: v for k, v in summary_data.items() if k not in ["자산증감액", "총평가금액"]}
        # 또는, 필요한 키만 선택하는 방식도 좋습니다.
        # 여기서는 원본 코드의 pop 방식을 유지하되, 키 존재 여부 확인
        if "자산증감액" in summary_data:
            summary_data.pop("자산증감액")
        if "총평가금액" in summary_data:  # 이 키는 /total_asset/summary에서 사용되므로 여기서 제거하는 것이 맞는지 확인 필요
            summary_data.pop("총평가금액")

        return jsonify({
            "stocks": stocks_list,
            "summary": summary_data  # 수정된 summary
        }), 200
    except Exception as e:
        app.logger.error(f"Error in /holdings/detail: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/stock/list", methods=["GET"])
def get_stock_list():
    try:
        if stock_df.empty:
            app.logger.warning("/stock/list: Global stock_df is empty.")
            return jsonify({"error": "주식 목록 데이터를 사용할 수 없습니다."}), 503  # Service Unavailable

        if not {'Code', 'Name'}.issubset(stock_df.columns):
            app.logger.error("/stock/list: Global stock_df is missing 'Code' or 'Name' columns.")
            return jsonify({"error": "주식 목록 데이터 형식이 올바르지 않습니다."}), 500

        # 전역 stock_df 사용
        renamed_stock_list = stock_df[["Code", "Name"]].rename(
            columns={"Code": "code", "Name": "name"}
        ).to_dict(orient="records")

        return Response(
            json.dumps(renamed_stock_list, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        app.logger.error(f"Error in /stock/list: {str(e)}", exc_info=True)
        return jsonify({"error": "주식 목록을 가져오는 중 오류 발생"}), 500


@app.route('/total_asset/summary', methods=['GET'])
def total_asset_summary():
    try:
        result = api.get_holdings_detailed()  # API 호출
        if result is None or "summary" not in result:
            return jsonify({"error": "자산 요약 정보를 찾을 수 없습니다."}), 404

        summary = result["summary"]
        keys_to_include = [
            "예수금총금액", "익일정산금액", "가수도정산금액",
            "총평가금액",  # 이 키는 /holdings/detail 에서 pop 되었을 수 있으므로 주의
            "금일매수수량", "금일매도수량", "금일제비용금액"
        ]

        # summary에 총평가금액이 없을 경우를 대비 (만약 /holdings/detail에서 pop 되었다면)
        # 이 경우, api.get_holdings_detailed()를 다시 호출하거나, pop하지 않도록 로직 조정 필요
        # 여기서는 summary에 해당 키가 있다는 가정하에 진행

        filtered_summary = {
            k: str(summary.get(k)) if summary.get(k) is not None else "0"
            for k in keys_to_include
        }
        # 또는 summary.get(k, "0") 을 사용하여 None일 경우 "0"으로 대체
        # filtered_summary = {k: str(summary.get(k, "0")) for k in keys_to_include}

        return Response(
            json.dumps(filtered_summary, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        app.logger.error(f"Error in /total_asset/summary: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/buy', methods=['POST'])
def buy_stock():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "요청 본문이 비어있거나 JSON 형식이 아닙니다."}), 400

        stock_code = data.get("stock_code")
        quantity_str = data.get("quantity")  # 수량은 정수형으로 변환 필요
        price_str = data.get("price")  # 가격도 정수형 또는 문자열(지정가 아닌 경우)
        order_type = data.get("order_type")  # 예: "00" (지정가), "01" (시장가)

        missing_fields = []
        if not stock_code: missing_fields.append("stock_code")
        if quantity_str is None: missing_fields.append("quantity")  # None 체크
        if price_str is None: missing_fields.append("price")  # None 체크
        if not order_type: missing_fields.append("order_type")

        if missing_fields:
            return jsonify({"success": False, "message": f"필수 필드 누락: {', '.join(missing_fields)}"}), 400

        try:
            quantity = int(quantity_str)
            # 가격은 주문 유형에 따라 다를 수 있음. 시장가의 경우 0 또는 특정 문자열일 수 있음.
            # 여기서는 문자열로 전달한다고 가정하고, API 내부에서 처리한다고 가정.
            # 필요시 int(price_str) 또는 float(price_str) 변환.
            price = str(price_str)  # API.do_buy가 문자열 가격을 처리한다고 가정
            if quantity <= 0:
                return jsonify({"success": False, "message": "수량은 0보다 커야 합니다."}), 400
        except ValueError:
            return jsonify({"success": False, "message": "수량 또는 가격 형식이 올바르지 않습니다."}), 400

        response = api.do_buy(stock_code, quantity, price, order_type)

        if response is None:
            app.logger.error("API call to do_buy returned None.")
            return jsonify({"success": False, "message": "매수 API 호출 중 응답을 받지 못했습니다."}), 500  # Internal Server Error

        if not response.is_ok():
            # KIS API가 반환한 오류 (예: 잔고 부족, 잘못된 종목 코드 등)
            # 클라이언트 측에서 조치 가능한 오류일 수 있으므로 4xx 상태 코드 사용
            status_code = 400  # 기본적으로 Bad Request, KIS 오류 코드에 따라 세분화 가능
            # 예: response.get_error_code()에 따라 422 (Unprocessable Entity) 등
            return jsonify({
                "success": False,
                "code": response.get_error_code(),
                "message": response.get_error_message()
            }), status_code

        body = response.get_body()
        # body가 객체이고 __dict__를 통해 dict 변환이 필요하면 사용, 아니면 그대로 사용
        response_data = body.__dict__ if hasattr(body, '__dict__') and not isinstance(body, dict) else body

        return jsonify({
            "success": True,
            "message": "매수 요청이 정상적으로 처리되었습니다.",  # 주문 제출 성공 의미
            "data": response_data
        }), 200  # 성공 시 200 OK 또는 201 Created (자원 생성된 경우)

    except Exception as e:
        app.logger.error(f"Unhandled exception in /buy: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"서버 처리 중 예외 발생: {str(e)}"}), 500


if __name__ == '__main__':
    # SSL 사용 시: app.run(host='0.0.0.0', port=5051, ssl_context=('path/to/cert.pem', 'path/to/key.pem'))
    app.run(host='0.0.0.0', port=5051, debug=bool(DEBUG))  # Flask의 debug 모드를 DEBUG 변수와 연동