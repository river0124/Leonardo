# flask_server.py
import json
import os
import pandas as pd
from flask import Flask, request, jsonify, Response

from get_asset import get_total_asset
from get_candle_data import get_candle_chart_data
from watchlist_store import load_watchlist, add_code_to_watchlist, remove_code_from_watchlist
from utils import KoreaInvestEnv, KoreaInvestAPI
from stock_name_finder import get_stock_name_by_code

DEBUG = 0  # Set to 1 to enable print, 0 to disable

# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "cache", "settings.json")
STOCK_LIST_CSV = os.path.join(BASE_DIR, "cache", "stock_list.csv")

# 설정 불러오기
def load_settings():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# 설정 저장
def save_settings(settings_dict: dict):
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = {}

    existing.update(settings_dict)

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

# Flask 앱 초기화
app = Flask(__name__)

# 초기 설정 및 API 객체 생성
cfg = load_settings()
if DEBUG:
    print("🐞 cfg loaded:", cfg)

env = KoreaInvestEnv(cfg)
api = KoreaInvestAPI(cfg=env.get_full_config(), base_headers=env.get_base_headers())

stock_df = pd.read_csv(STOCK_LIST_CSV, dtype=str)

@app.route('/candle', methods=['GET'])
def candle():
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Missing code parameter"}), 400

    try:
        result = get_candle_chart_data(code)
        candles = result.get("candles", [])
        valid_candles = [c for c in candles if all(c.get(k) is not None and c.get(k) >= 0 for k in ['open', 'high', 'low', 'close'])]

        if DEBUG:
            print("🛠 필터 전 캔들 수:", len(candles))
            print("🛠 필터 후 캔들 수:", len(valid_candles))
            print("\n=== 서버 응답 데이터 ===")
            print("요청된 종목 코드:", code)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("========================\n")

        result["candles"] = valid_candles
        return jsonify(result), 200
    except Exception as e:
        if DEBUG:
            print(f"서버 에러 발생: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/asset', methods=['GET'])
def asset():
    try:
        total_asset = get_total_asset()
        if total_asset is None:
            return jsonify({"error": "총자산을 불러올 수 없습니다."}), 500
        return jsonify({"balance": str(total_asset)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/high52", methods=["GET"])
def high52():
    try:
        with open(os.path.join(BASE_DIR, "cache", "high52.json"), encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/price', methods=['GET'])
def get_price():
    stock_no = request.args.get('stock_no')
    if not stock_no:
        return jsonify({"error": "stock_no is required"}), 400
    try:
        data = api.get_current_price(stock_no)
        stock_name = stock_df.loc[stock_df['Code'] == stock_no, 'Name'].values
        stock_name = stock_name[0] if len(stock_name) > 0 else "이름없음"
        filtered = {
            "name": stock_name,
            "stck_prpr": data.get("stck_prpr"),
            "stck_oprc": data.get("stck_oprc"),
            "stck_hgpr": data.get("stck_hgpr"),
            "stck_lwpr": data.get("stck_lwpr"),
            "prdy_vrss": data.get("prdy_vrss"),
            "prdy_ctrt": data.get("prdy_ctrt"),
            "acml_vol": data.get("acml_vol"),
            "hts_avls": data.get("hts_avls"),
            "w52_hgpr": data.get("w52_hgpr"),
            "w52_lwpr": data.get("w52_lwpr")
        }
        return Response(
            json.dumps(filtered, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/watchlist", methods=["GET", "POST", "DELETE"])
def watchlist():
    try:
        if request.method == "GET":
            return jsonify({"watchlist": load_watchlist()})

        data = request.get_json()
        code = data.get("code")

        if not code:
            return jsonify({"error": "Missing 'code' field in request"}), 400

        if request.method == "POST":
            add_code_to_watchlist(code)
            return jsonify({"message": f"{code} added to watchlist."}), 200

        if request.method == "DELETE":
            remove_code_from_watchlist(code)
            return jsonify({"message": f"{code} removed from watchlist."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stockname', methods=['GET'])
def stockname():
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Missing code parameter"}), 400

    name = get_stock_name_by_code(code)
    if name:
        return jsonify({"code": code, "name": name})
    else:
        return jsonify({"error": "Stock name not found"}), 404

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'GET':
        try:
            return jsonify(load_settings()), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            data = request.get_json()
            if DEBUG:
                print("📩 POST /settings 요청 수신:", data)

            save_settings(data)
            return jsonify({"message": "Settings saved successfully"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# /holdings/detail endpoint
@app.route('/holdings/detail', methods=['GET'])
def holdings_detail():
    try:
        result = api.get_holdings_detailed()
        if result is None:
            return jsonify({"error": "No holdings found"}), 404

        stocks = result["stocks"]
        summary = result["summary"]

        if isinstance(stocks, pd.DataFrame) and not stocks.empty:
            stocks = stocks.drop(columns=["trad_dvsn_name"], errors="ignore").to_dict(orient="records")

        # Remove unwanted keys from summary
        summary.pop("자산증감액", None)
        summary.pop("총평가금액", None)

        return jsonify({
            "stocks": stocks,
            "summary": summary
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stock/list", methods=["GET"])
def get_stock_list():
    try:
        csv_path = os.path.join(BASE_DIR, "cache", "stock_list.csv")
        df = pd.read_csv(csv_path, dtype=str)
        stock_list = df[["Code", "Name"]].rename(columns={"Code": "code", "Name": "name"}).to_dict(orient="records")
        return Response(
            json.dumps(stock_list, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# /total_asset/summary endpoint
@app.route('/total_asset/summary', methods=['GET'])
def total_asset_summary():
    try:
        result = api.get_holdings_detailed()
        if result is None or "summary" not in result:
            return jsonify({"error": "Summary data not found"}), 404

        summary = result["summary"]
        keys_to_include = [
            "예수금총금액",
            "익일정산금액",
            "가수도정산금액",
            "총평가금액",
            "금일매수수량",
            "금일매도수량",
            "금일제비용금액"
        ]

        filtered_summary = {k: summary.get(k) or "0" for k in keys_to_include}
        return Response(
            json.dumps(filtered_summary, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/buy', methods=['POST'])
def buy_stock():
    try:
        data = request.get_json()
        stock_code = data.get("stock_code")
        quantity = data.get("quantity")
        price = data.get("price")
        order_type = data.get("order_type")

        if not stock_code or quantity is None or price is None or order_type is None:
            return jsonify({"success": False, "message": "Missing required fields"}), 400

        response = api.do_buy(stock_code, quantity, price, order_type)

        if response is not None:
            if not response.is_ok():
                message = response.get_error_message()
                code = response.get_error_code()
                return jsonify({
                    "success": False,
                    "code": code,
                    "message": message
                }), 200
            return jsonify({
                "success": True,
                "message": "매수 요청이 정상적으로 처리되었습니다.",
                "data": response.get_body().__dict__
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "서버 오류: 응답이 없습니다."
            }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"서버 예외: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5051)