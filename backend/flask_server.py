# flask_server.py
import json
from flask import Flask, request, jsonify, Response
from get_asset import get_total_asset
from get_candle_data import get_candle_chart_data
from watchlist_store import load_watchlist, add_code_to_watchlist, remove_code_from_watchlist
from utils import KoreaInvestEnv, KoreaInvestAPI
import yaml
import pandas as pd
from stock_name_finder import get_stock_name_by_code

DEBUG = 0  # Set to 1 to enable print, 0 to disable

# YAML 설정 불러오기
with open("/Users/hyungseoklee/Documents/Leonardo/backend/config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

# 투자 환경 및 API 초기화
env = KoreaInvestEnv(cfg)
api = KoreaInvestAPI(cfg=env.get_full_config(), base_headers=env.get_base_headers())

stock_df = pd.read_csv("/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv", dtype=str)

# Flask 앱 초기화
app = Flask(__name__)

@app.route('/candle', methods=['GET'])
def candle():
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Missing code parameter"}), 400

    try:
        result = get_candle_chart_data(code)

        candles = result.get("candles", [])
        valid_candles = [c for c in candles if all(c.get(k) is not None and c.get(k) >= 0 for k in ['open', 'high', 'low', 'close'])]
        if DEBUG: print("🛠 필터 전 캔들 수:", len(candles))
        if DEBUG: print("🛠 필터 후 캔들 수:", len(valid_candles))

        if not valid_candles:
            return jsonify({"error": "No valid candle data"}), 500

        result["candles"] = valid_candles

        import json
        if DEBUG:
            print("\n=== 서버 응답 데이터 ===")
            print("요청된 종목 코드:", code)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("========================\n")

        return jsonify(result), 200
    except Exception as e:
        if DEBUG: print(f"서버 에러 발생: {str(e)}")
        return jsonify({"error": str(e)}), 500

# /asset endpoint
@app.route('/asset', methods=['GET'])
def asset():
    try:
        total_asset = get_total_asset()
        if total_asset is None:
            return jsonify({"error": "총자산을 불러올 수 없습니다."}), 500
        return jsonify({"balance": str(total_asset)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# /52주 신고가 endpoint
@app.route("/high52", methods=["GET"])
def high52():
    try:
        with open("/Users/hyungseoklee/Documents/Leonardo/backend/cache/high52.json", encoding="utf-8") as f:
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


# New endpoint to get stock name by code
@app.route('/stockname', methods=['GET'])
def stockname():
    code = request.args.get('code')
    if not code:
        return Response(
            json.dumps({"error": "Missing code parameter"}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )

    name = get_stock_name_by_code(code)
    if name:
        return Response(
            json.dumps({"code": code, "name": name}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    else:
        return Response(
            json.dumps({"error": "Stock name not found"}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )


# /holdings endpoint
@app.route('/holdings', methods=['GET'])
def holdings():
    try:
        df = api.get_holdings()
        if df.empty:
            return jsonify({"error": "No holdings found"}), 404

        # 필요한 컬럼만 JSON으로 반환
        df_filtered = df[[
            "pdno", "prdt_name", "hldg_qty", "ord_psbl_qty", "pchs_avg_pric",
            "prpr", "evlu_amt", "evlu_pfls_amt", "evlu_pfls_rt"
        ]].rename(columns={
            "pdno": "code",
            "prdt_name": "name",
            "hldg_qty": "quantity",
            "ord_psbl_qty": "available_quantity",
            "pchs_avg_pric": "avg_price",
            "prpr": "current_price",
            "evlu_amt": "evaluation_amount",
            "evlu_pfls_amt": "profit_loss",
            "evlu_pfls_rt": "profit_loss_rate"
        })

        numeric_columns = [
            "quantity", "available_quantity", "avg_price",
            "current_price", "evaluation_amount", "profit_loss", "profit_loss_rate"
        ]
        df_filtered[numeric_columns] = df_filtered[numeric_columns].apply(pd.to_numeric, errors='coerce')

        return Response(
            df_filtered.to_json(orient="records", force_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5051)