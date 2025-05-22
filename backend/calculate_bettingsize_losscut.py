import json
from get_asset import get_total_asset
from calculate_atr import calculate_atr
import FinanceDataReader as fdr
from hoga_scale import adjust_price_to_hoga

def main():
    try:
        total_asset = get_total_asset()
        if total_asset is None:
            print(json.dumps({"error": "총자산을 불러올 수 없습니다."}))
            return

        stock_code = input().strip()
        period = int(input().strip())
        loss_percent_input = float(input().strip())

        loss_percent = abs(loss_percent_input) / 100
        display_loss_ratio = f"{'-' if loss_percent_input > 0 else ''}{abs(loss_percent_input):.2f}%"

        atr = calculate_atr(stock_code, period, return_only=True)
        if atr is None or atr == 0:
            print(json.dumps({"error": "ATR 계산 실패 또는 0"}))
            return

        risk_amount = total_asset * loss_percent
        unit = int(risk_amount / atr)
        if unit <= 0:
            print(json.dumps({"error": "매수 수량이 0 이하입니다. 손실 비율 또는 자산을 확인하세요."}))
            return

        df = fdr.DataReader(stock_code)
        current_price = float(df['Close'].iloc[-1])
        stop_loss_price = int(adjust_price_to_hoga(current_price - atr, method='floor'))
        invested_amount = unit * current_price
        invested_ratio = (invested_amount / total_asset) * 100

        # 투입비중이 80%를 넘는 경우 비중을 맞춰서 매수 수량 조정
        max_ratio = 80
        if invested_ratio > max_ratio:
            adjusted_unit = int((total_asset * max_ratio / 100) / current_price)
            invested_amount = adjusted_unit * current_price
            invested_ratio = (invested_amount / total_asset) * 100
            unit = adjusted_unit
            message = f"⚠️ 투입 비중이 {max_ratio}%를 초과하여 자동 조정되었습니다."
        else:
            message = ""

        # ✅ 모든 값을 문자열로 변환해서 JSON 출력
        print(json.dumps({
            "asset": f"{total_asset}",
            "risk_ratio": display_loss_ratio,
            "atr": f"{int(atr)}",
            "unit": f"{unit}",
            "current_price": f"{round(current_price)}",
            "stop_loss_price": f"{stop_loss_price}",
            "invested_amount": f"{round(invested_amount)}",
            "invested_ratio": f"{invested_ratio:.2f}%",
            "message": message
        }))

    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()