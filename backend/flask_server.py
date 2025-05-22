# flask_server.py
import json
from flask import Flask, request, jsonify
from get_asset import get_total_asset
from get_candle_data import get_candle_chart_data
from find_52week_high_candidates import find_52week_high_candidates

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
        print("🛠 필터 전 캔들 수:", len(candles))
        print("🛠 필터 후 캔들 수:", len(valid_candles))

        if not valid_candles:
            return jsonify({"error": "No valid candle data"}), 500

        result["candles"] = valid_candles

        import json
        print("\n=== 서버 응답 데이터 ===")
        print("요청된 종목 코드:", code)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("========================\n")

        return jsonify(result), 200
    except Exception as e:
        print(f"서버 에러 발생: {str(e)}")
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5051)