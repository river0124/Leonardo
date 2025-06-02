# test_notify_integration.py
import requests

def test_notify_integration():
    # Flask 서버가 실행 중이어야 합니다.
    buy_payload = {
        "stock_code": "005930",
        "quantity": 10,
        "price": "0",
        "order_type": "시장가",
        "atr": 250.0
    }
    notify_payload = {
        "body": {
            "rt_cd": "0",
            "msg_cd": "0000",
            "msg1": "체결완료",
            "output": {
                "ord_no": "0000001",
                "tr_qty": "10",
                "tr_price": "82700",
                "code": "005930"
            }
        }
    }

    buy_resp = requests.post("http://127.0.0.1:5000/buy", json=buy_payload)
    assert buy_resp.status_code == 202
    assert buy_resp.json()["success"] is True

    notify_resp = requests.post("http://127.0.0.1:5000/test/notify", json=notify_payload)
    assert notify_resp.status_code == 200
    assert notify_resp.json()["message"].startswith("✅ 테스트 메시지 송신 완료")