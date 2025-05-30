# flask_server_backup.py
# import json
# import datetime
# import os
# import pandas as pd
# import asyncio
# from flask import Flask, request, jsonify, Response
# from cryptography.fernet import Fernet
# from trade_manager_backup import TradeManager
# # import logging # app.logger.setLevel을 사용하려면 필요
#
# from get_asset import get_total_asset
# from get_candle_data import get_candle_chart_data
# from watchlist_store import load_watchlist, add_code_to_watchlist, remove_code_from_watchlist
# from utils import KoreaInvestEnv, KoreaInvestAPI
# from stock_name_finder import get_stock_name_by_code
# from loguru import logger
#
# DEBUG = 0  # Set to 1 to enable print, 0 to disable
#
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CACHE_DIR = os.path.join(BASE_DIR, "cache")
# SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")
# STOCK_LIST_CSV = os.path.join(CACHE_DIR, "stock_list.csv")
#
# # Fernet encryption setup
# FERNET_KEY_FILE = os.path.join(CACHE_DIR, "key.secret")
# if os.path.exists(FERNET_KEY_FILE):
#     with open(FERNET_KEY_FILE, "rb") as f:
#         FERNET_KEY = f.read()
# else:
#     FERNET_KEY = Fernet.generate_key()
#     os.makedirs(CACHE_DIR, exist_ok=True)
#     with open(FERNET_KEY_FILE, "wb") as f:
#         f.write(FERNET_KEY)
# fernet = Fernet(FERNET_KEY)

# Flask 앱 초기화
# app = Flask(__name__)


# 로깅 레벨 설정 (선택 사항)
# if DEBUG:
#     app.logger.setLevel(logging.DEBUG)
# else:
#     app.logger.setLevel(logging.INFO)

# # 설정 불러오기
# def load_settings():
#     if os.path.exists(SETTINGS_FILE):
#         try:
#             with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
#                 settings = json.load(f)
#             # Decrypt sensitive fields
#             for key in ["api_key", "access_token"]:
#                 if key in settings and isinstance(settings[key], str):
#                     try:
#                         settings[key] = fernet.decrypt(settings[key].encode()).decode()
#                     except Exception:
#                         pass  # If not decryptable, leave as is
#             return settings
#         except json.JSONDecodeError:
#             app.logger.warning(f"Warning: Could not decode JSON from {SETTINGS_FILE}. Returning empty settings.")
#             return {}
#     return {}





# # --- Helper for order validation ---
# def validate_order_request(data, require_atr=False):
#     if not data:
#         return False, "요청 본문이 비어있거나 JSON 형식이 아닙니다."
#
#     stock_code = data.get("stock_code")
#     quantity_str = data.get("quantity")
#     price_str = data.get("price")
#     order_type = data.get("order_type")
#     atr_str = data.get("atr") if require_atr else None
#
#     missing_fields = []
#     if not stock_code: missing_fields.append("stock_code")
#     if quantity_str is None: missing_fields.append("quantity")
#     if price_str is None: missing_fields.append("price")
#     if not order_type: missing_fields.append("order_type")
#     if require_atr and atr_str is None: missing_fields.append("atr")
#
#     if missing_fields:
#         return False, f"필수 필드 누락: {', '.join(missing_fields)}"
#
#     try:
#         quantity = int(quantity_str)
#         price = str(price_str)
#         if quantity <= 0:
#             return False, "수량은 0보다 커야 합니다."
#     except ValueError:
#         return False, "수량 또는 가격 형식이 올바르지 않습니다."
#
#     if require_atr:
#         try:
#             atr = float(atr_str)
#         except ValueError:
#             return False, "ATR 값이 숫자가 아닙니다."
#     else:
#         atr = None
#
#     return True, {
#         "stock_code": stock_code,
#         "quantity": quantity,
#         "price": price,
#         "order_type": order_type,
#         "atr": atr
#     }


# # 초기 설정 및 API 객체 생성
# cfg = load_settings()
# if DEBUG:
#     print("🐞 cfg loaded:", cfg)

# env = KoreaInvestEnv(cfg)
# api = KoreaInvestAPI(cfg=env.get_full_config(), base_headers=env.get_base_headers())
# trade_manager = TradeManager(api, cfg)

# 주식 목록 CSV 파일 로드
# try:
#     stock_df = pd.read_csv(STOCK_LIST_CSV, dtype=str)
# except FileNotFoundError:
#     app.logger.error(f"Fatal: Stock list file not found at {STOCK_LIST_CSV}. Some functionalities might not work.")
#     stock_df = pd.DataFrame(columns=['Code', 'Name'])  # 빈 DataFrame으로 초기화하여 이후 코드 실행 보장
# except Exception as e:
#     app.logger.error(f"Fatal: Error loading stock list {STOCK_LIST_CSV}: {e}")
#     stock_df = pd.DataFrame(columns=['Code', 'Name'])
























@app.route('/buy', methods=['POST'])
def buy_stock():
    try:

        is_valid, result = validate_order_request(request.get_json(), require_atr=True)
        if not is_valid:
            return jsonify({"success": False, "message": result}), 400

        order = result
        response = trade_manager.place_order_with_stoploss(
            order["stock_code"], order["quantity"], order["price"], order["atr"], order["order_type"]
        )
        app.logger.info(f"📈 매수 주문 완료: {order['stock_code']} | 수량: {order['quantity']} | 가격: {order['price']} | ATR: {order['atr']}")

        if "error" in response:
            return jsonify({"success": False, "message": response["error"]}), 500

        return jsonify({
            "success": True,
            "message": "매수 요청이 정상적으로 처리되었습니다.",
            "data": response
        }), 200
    except Exception as e:
        app.logger.error(f"Unhandled exception in /buy: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"서버 처리 중 예외 발생: {str(e)}"}), 500

@app.route('/sell', methods=['POST'])
def sell_stock():
    try:
        is_valid, result = validate_order_request(request.get_json())
        if not is_valid:
            return jsonify({"success": False, "message": result}), 400

        order = result
        response = api.do_sell(order["stock_code"], order["quantity"], order["price"], order["order_type"])

        if response and response.is_ok():
            return jsonify({
                "success": True,
                "message": "매도 요청이 정상적으로 처리되었습니다.",
                "data": response.get_body()
            }), 200
        else:
            error_msg = response.get_error_message() if response else "API 응답 없음"
            return jsonify({"success": False, "message": f"매도 요청 실패: {error_msg}"}), 500

    except Exception as e:
        app.logger.error(f"Unhandled exception in /sell: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"서버 처리 중 예외 발생: {str(e)}"}), 500




# ---- RISK STATUS ROUTE ----
@app.route('/risk_status', methods=['GET'])
def risk_status():
    return jsonify(trade_manager.export_risk_state())


if __name__ == '__main__':
    import threading
    # from websocket_manager import WebSocketManager
    #
    # websocket_url = cfg.get("websocket_url")
    # websocket_manager = WebSocketManager(api, websocket_url, env)
    #
    # # ✅ 웹소켓을 백그라운드에서 상시 유지
    # threading.Thread(target=websocket_manager.run_forever, daemon=True).start()

    # ✅ 주문 체결 모니터링도 병렬 실행
    threading.Thread(target=trade_manager.process_execution_queue, daemon=True).start()

    app.run(host='0.0.0.0', port=5051, debug=bool(DEBUG))