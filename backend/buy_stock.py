import sys
from utils_backup import KoreaInvestEnv, KoreaInvestAPI
from settings_manager import load_settings

def main():
    if len(sys.argv) < 4:
        print("사용법: python buy_stock.py 종목코드 수량 주문타입 [지정가]")
        print("예시 (지정가): python buy_stock.py 005930 1 00 88000")
        print("예시 (시장가): python buy_stock.py 005930 1 01")
        return

    stock_code = sys.argv[1]
    quantity = int(sys.argv[2])
    order_type = sys.argv[3]  # "00" (지정가), "01" (시장가)

    # 지정가일 경우 가격 필요
    if order_type == "00":
        if len(sys.argv) < 5:
            print("지정가 주문은 가격이 필요합니다.")
            return
        order_price = int(sys.argv[4])
    else:
        order_price = 0  # 시장가 주문 시 가격은 0

    # 설정 파일 로드 및 API 초기화
    cfg = load_settings()

    env_cls = KoreaInvestEnv(cfg)
    base_headers = env_cls.get_base_headers()
    cfg = env_cls.get_full_config()
    korea_invest_api = KoreaInvestAPI(cfg, base_headers=base_headers)

    # 매수 주문 실행
    res = korea_invest_api.do_buy(
        stock_code,
        order_qty=quantity,
        order_price=order_price,
        order_type=order_type
    )

    # 결과 출력
    print(f"주문 결과: {res.get_body()}")
    try:
        order_num = res.get_body().output["ODNO"]
        print(f"주문번호: {order_num}")
    except Exception as e:
        print("주문번호 가져오기 실패:", e)

if __name__ == "__main__":
    main()