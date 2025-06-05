# flask_server.py

from flask import Flask, jsonify, request, Response
import threading
import asyncio
import sys
import json
import datetime
import os
from dotenv import load_dotenv
import pandas as pd
from cryptography.fernet import Fernet
from settings import cfg

load_dotenv(dotenv_path='.env.local')  # .env.local 파일에서 환경변수 로드

from get_asset import get_total_asset
from get_candle_data import get_candle_chart_data
from watchlist_store import load_watchlist, add_code_to_watchlist, remove_code_from_watchlist
from utils import KoreaInvestEnv, KoreaInvestAPI
from stock_name_finder import get_stock_name_by_code
from trade_manager import TradeManager
from settings import load_settings, save_settings
from loguru import logger

# --- 경로 설정 ---
APP_ENV = os.getenv('APP_ENV', 'local')

if APP_ENV == 'local':
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CACHE_DIR = os.path.join(BASE_DIR, 'cache')
else:  # server
    BASE_DIR = '/home/ubuntu/backend'
    CACHE_DIR = os.path.join(BASE_DIR, 'cache')

SETTINGS_FILE = os.path.join(CACHE_DIR, 'settings.json')
STOCK_LIST_CSV = os.path.join(CACHE_DIR, 'stock_list.csv')
FERNET_KEY_FILE = os.path.join(CACHE_DIR, 'key.secret')

# --- 암호화 키 준비 ---
if os.path.exists(FERNET_KEY_FILE):
    with open(FERNET_KEY_FILE, "rb") as f:
        FERNET_KEY = f.read()
else:
    FERNET_KEY = Fernet.generate_key()
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(FERNET_KEY_FILE, "wb") as f:
        f.write(FERNET_KEY)
fernet = Fernet(FERNET_KEY)

# --- Flask 앱 초기화 ---
app = Flask(__name__)

# --- 비동기 큐 및 이벤트 루프 설정 ---
execution_queue = asyncio.Queue()
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


# 디버깅 모드 설정
DEBUG = cfg.get("DEBUG", "False").lower() == "true"
if DEBUG:
    logger.info("🐞 cfg 로딩 완료: {}", cfg)

logger.remove()
logger.add(sys.stderr, level="DEBUG" if DEBUG else "WARNING")

# --- 주문 유효성 검사 도우미 ---
def validate_order_request(data, require_atr=False):
    if not data:
        return False, "요청 본문이 비어있거나 JSON 형식이 아닙니다."
    stock_code = data.get("stock_code")
    quantity_str = data.get("quantity")
    price_str = data.get("price")
    order_type = data.get("order_type")
    atr_str = data.get("atr") if require_atr else None

    missing_fields = []
    if not stock_code: missing_fields.append("stock_code")
    if quantity_str is None: missing_fields.append("quantity")
    if price_str is None: missing_fields.append("price")
    if not order_type: missing_fields.append("order_type")
    if require_atr and atr_str is None: missing_fields.append("atr")

    if missing_fields:
        return False, f"필수 필드 누락: {', '.join(missing_fields)}"

    try:
        quantity = int(quantity_str)
        price = str(price_str)
        if quantity <= 0:
            return False, "수량은 0보다 커야 합니다."
    except ValueError:
        return False, "수량 또는 가격 형식이 올바르지 않습니다."

    if require_atr:
        try:
            atr = float(atr_str)
        except ValueError:
            return False, "ATR 값이 숫자가 아닙니다."
    else:
        atr = None

    return True, {
        "stock_code": stock_code,
        "quantity": quantity,
        "price": price,
        "order_type": order_type,
        "atr": atr
    }

# --- 주식 리스트 로드 ---
try:
    stock_df = pd.read_csv(STOCK_LIST_CSV, dtype=str)
except FileNotFoundError:
    if DEBUG:
        logger.error(f"📛 주식 리스트 파일이 존재하지 않습니다: {STOCK_LIST_CSV}")
    stock_df = pd.DataFrame(columns=['Code', 'Name'])
except Exception as e:
    if DEBUG:
        logger.error(f"📛 주식 리스트 파일 로딩 실패: {e}")
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
        if DEBUG:
            logger.error(f"Error in /candle for code {code}: {str(e)}", exc_info=True)
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
        if DEBUG:
            logger.error(f"Error in /asset: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/high52", methods=["GET"])
def high52():
    try:
        # HIGH52_JSON_FILE = os.path.join(CACHE_DIR, "high52.json") # 변수 사용 권장
        with open(os.path.join(CACHE_DIR, "high52.json"), encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    except FileNotFoundError:
        if DEBUG:
            logger.warning(f"/high52: high52.json not found.")
        return jsonify({"error": "52주 신고가 데이터를 찾을 수 없습니다."}), 404
    except Exception as e:
        if DEBUG:
            logger.error(f"Error in /high52: {str(e)}", exc_info=True)
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
            if DEBUG:
                logger.warning("Stock dataframe is empty or missing columns for name lookup in /price.")

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
        if DEBUG:
            logger.error(f"Error in /price for stock_no {stock_no}: {str(e)}", exc_info=True)
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
        if DEBUG:
            logger.error(f"Error in /watchlist: {str(e)}", exc_info=True)
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


# Combined GET and POST /settings route to support retrieving and saving settings
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        try:
            settings = request.get_json()
            if not settings:
                return jsonify({"error": "Invalid settings data"}), 400

            save_settings(settings)

            global env, api, trade_manager
            cfg = load_settings()
            env = KoreaInvestEnv(cfg)

            api = KoreaInvestAPI(cfg=env.get_full_config(), base_headers=env.get_base_headers(), websocket_approval_key=cfg['approval_key'])
            trade_manager = TradeManager(api, cfg, approval_key=cfg['approval_key'])

            if DEBUG:
                logger.debug(f"⚙️ Settings updated. Mode: {'모의투자' if cfg.get('is_paper_trading') else '실전투자'}")
            return jsonify({"message": "Settings saved successfully"}), 200
        except Exception as e:
            if DEBUG:
                logger.error(f"Error saving settings: {e}", exc_info=True)
            return jsonify({"error": "Failed to save settings"}), 500

    elif request.method == "GET":
        try:
            cfg = load_settings()
            return jsonify(cfg), 200
        except Exception as e:
            if DEBUG:
                logger.error(f"Error loading settings: {e}", exc_info=True)
            return jsonify({"error": "Failed to load settings"}), 500


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
        if "자산증감액" in summary_data:
            summary_data.pop("자산증감액")
        if "총평가금액" in summary_data:
            summary_data.pop("총평가금액")

        return jsonify({
            "stocks": stocks_list,
            "summary": summary_data,
            "is_empty": len(stocks_list) == 0
        }), 200
    except Exception as e:
        if DEBUG:
            logger.error(f"Error in /holdings/detail: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/holdings")
def get_holdings():
    try:
        from utils import create_env_api  # ensure this import exists at the top if not already
        env, api = create_env_api()  # Re-initialize per request
        result = api.get_holdings_detailed()
        if result is None or "stocks" not in result:
            return jsonify({"error": "보유 종목 정보를 가져올 수 없습니다."}), 404

        stocks_data = result["stocks"]
        if isinstance(stocks_data, pd.DataFrame):
            stocks_list = stocks_data.to_dict(orient="records")
        elif isinstance(stocks_data, list):
            stocks_list = stocks_data
        else:
            stocks_list = []

        return jsonify(stocks_list), 200
    except Exception as e:
        if DEBUG:
            logger.error(f"Error in /holdings: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/stock/list", methods=["GET"])
def get_stock_list():
    try:
        if stock_df.empty:
            if DEBUG:
                logger.warning("/stock/list: Global stock_df is empty.")
            return jsonify({"error": "주식 목록 데이터를 사용할 수 없습니다."}), 503  # Service Unavailable

        if not {'Code', 'Name'}.issubset(stock_df.columns):
            if DEBUG:
                logger.error("/stock/list: Global stock_df is missing 'Code' or 'Name' columns.")
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
        if DEBUG:
            logger.error(f"Error in /stock/list: {str(e)}", exc_info=True)
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
            k: str(summary.get(k)) if summary.get(k) is not None else "None"
            for k in keys_to_include
        }
        # 또는 summary.get(k, "0") 을 사용하여 None일 경우 "0"으로 대체
        # filtered_summary = {k: str(summary.get(k, "0")) for k in keys_to_include}

        return Response(
            json.dumps(filtered_summary, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        if DEBUG:
            logger.error(f"Error in /total_asset/summary: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ---- MARKET OPEN STATUS ROUTE ----
@app.route("/market/is_open", methods=["GET"])
def is_market_open():
    try:
        now = datetime.datetime.now()
        today = now.date()
        weekday = today.weekday()  # 0: Monday ~ 6: Sunday

        if weekday >= 5:
            return jsonify({"market_open": False, "reason": "Weekend"}), 200

        holidays_path = os.path.join(CACHE_DIR, "holidays.csv")
        if os.path.exists(holidays_path):
            holidays_df = pd.read_csv(holidays_path, dtype=str)
            if "날짜" not in holidays_df.columns:
                return jsonify({"market_open": False, "error": "holidays.csv에 '날짜' 컬럼 없음"}), 500

            holiday_dates = set(pd.to_datetime(holidays_df["날짜"], format="%Y%m%d").dt.strftime("%Y-%m-%d").tolist())
            if today.strftime("%Y-%m-%d") in holiday_dates:
                return jsonify({"market_open": False, "reason": "Holiday"}), 200

        # ✅ 시간 조건 확장: 08:40 ~ 15:31 사이만 리프레시 허용
        market_refresh_start = now.replace(hour=8, minute=40, second=0, microsecond=0)
        market_refresh_end = now.replace(hour=15, minute=31, second=0, microsecond=0)

        if not (market_refresh_start <= now <= market_refresh_end):
            return jsonify({"market_open": False, "reason": "Outside refresh window"}), 200

        return jsonify({"market_open": True}), 200

    except Exception as e:
        if DEBUG:
            logger.error(f"Error in /market/is_open: {str(e)}", exc_info=True)
        return jsonify({"market_open": False, "error": str(e)}), 500


@app.route('/buy', methods=['POST'])
def buy_stock():
    try:
        is_valid, result = validate_order_request(request.get_json(), require_atr=True)
        if not is_valid:
            return jsonify({"success": False, "message": result}), 400

        order = result
        if DEBUG:
            logger.debug(f"[BUY API] 주문 요청 데이터: {json.dumps(order, ensure_ascii=False)}")


        asyncio.run_coroutine_threadsafe(
            execution_queue.put({
                "type": "buy",
                "stock_code": order["stock_code"],
                "qty": order["quantity"],
                "price": order["price"],
                "atr": order["atr"],
                "order_type": order["order_type"]
            }),
            loop
        )

        if DEBUG:
            logger.info(f"📥 매수 주문 큐에 등록됨: {order['stock_code']} | 수량: {order['quantity']} | 가격: {order['price']} | ATR: {order['atr']}")

        return jsonify({
            "success": True,
            "message": "매수 요청이 큐에 등록되었습니다. 체결 대기 중입니다."
        }), 202
    except Exception as e:
        if DEBUG:
            logger.error(f"Unhandled exception in /buy: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"서버 처리 중 예외 발생: {str(e)}"}), 500


# --- 앱 실행 ---
if __name__ == '__main__':
    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(
        cfg=cfg,
        base_headers=env.get_base_headers(),
        websocket_approval_key=cfg['websocket_approval_key']
    )

    execution_queue = asyncio.Queue()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    trade_manager = TradeManager(cfg, api, execution_queue)
    loop.create_task(trade_manager.process_execution_queue())

    threading.Thread(target=loop.run_forever, daemon=True).start()
    app.run(debug=True, use_reloader=False)

    # app.run(host="0.0.0.0", port=5000, debug=True)