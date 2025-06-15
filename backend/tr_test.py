from utils import KoreaInvestAPI
from settings import cfg
from is_paper_trading import set_is_paper_trading

DEBUG = cfg.get("DEBUG", "False").lower() == "true"

def get_current_price(stock_code):

    api = KoreaInvestAPI()
    output = api.current_price(stock_code)

    print(output)

def get_inquire_psbl_rvsecncl():
    original_mode = cfg.get("is_paper_trading", True)
    if original_mode == True:
        set_is_paper_trading(False)
        cfg["is_paper_trading"] = False

    api = KoreaInvestAPI()
    output = api.inquire_psbl_rvsecncl()

    if original_mode == True:
        set_is_paper_trading(True)
        cfg["is_paper_trading"] = True

    print(output)

def get_inquire_balance():

    api = KoreaInvestAPI()
    df1, df2 = api.inquire_balance()
    print("📄 보유 종목 목록 (output1):")
    print(df1)
    print("\n📊 계좌 평가 요약 (output2):")
    print(df2)

def buy_stock(stock_code, order_qty, order_price, order_type):
    api = KoreaInvestAPI()
    output = api.do_buy(stock_code, order_qty, order_price, order_type)
    print(output)

def sell_stock(stock_code, order_qty, order_price, order_type):
    api = KoreaInvestAPI()
    output = api.do_sell(stock_code, order_qty, order_price, order_type)
    print(output)


def order_revise():
    pass

def get_summarize_foreign_institution_estimates(stock_code):
    original_mode = cfg.get("is_paper_trading", True)
    if original_mode == True:
        set_is_paper_trading(False)
        cfg["is_paper_trading"] = False

    api = KoreaInvestAPI()
    output = api.summarize_foreign_institution_estimates(stock_code)

    if original_mode == True:
        set_is_paper_trading(True)
        cfg["is_paper_trading"] = True

    if output is not None and not output.empty:
        latest = output.sort_values("입력구분", ascending=False).iloc[0]
        frgn = int(latest["외국인수량(가집계)"])
        orgn = int(latest["기관수량(가집계)"])
        print(frgn, orgn)
    else:
        print("❗ 수급 요약 결과가 비어 있습니다.")

def get_current_price_and_investor(stock_code):
    api = KoreaInvestAPI()
    output = api.current_price_and_investor(stock_code)
    print(output)

def get_foreign_net_trading_summary(market):
    api = KoreaInvestAPI()
    output = api.foreign_net_trading_summary(market)
    print(output)

def get_program_trade_summary_by_time(stock_code, market):
    original_mode = cfg.get("is_paper_trading", True)
    if original_mode == True:
        set_is_paper_trading(False)
        cfg["is_paper_trading"] = False

    api = KoreaInvestAPI()
    output = api.program_trade_summary_by_time(stock_code, market)

    if original_mode == True:
        set_is_paper_trading(True)
        cfg["is_paper_trading"] = True

    print(output)

def get_summarize_foreign_net_estimates(stock_code):
    original_mode = cfg.get("is_paper_trading", True)
    if original_mode == True:
        set_is_paper_trading(False)
        cfg["is_paper_trading"] = False

    api = KoreaInvestAPI()
    output = api.summarize_foreign_net_estimates(stock_code)

    if original_mode == True:
        set_is_paper_trading(True)
        cfg["is_paper_trading"] = True

    print(output)


if __name__ == "__main__":
    stock_code = "005930"
    order_qty = "1"
    order_price = "58300"
    order_type = "00"
    order_num = ""
    # market = "1001" # 0000(전체), 1001(코스피), 2001(코스닥)
    market = "J" # KRX : J , NXT : NX, 통합 : UN
    # buy_stock(stock_code, order_qty, order_price, order_type)
    # sell_stock(stock_code, order_qty, order_price, order_type)
    get_current_price(stock_code)
    # get_inquire_psbl_rvsecncl()
    # get_inquire_balance()
    # get_summarize_foreign_institution_estimates(stock_code)
    # get_current_price_and_investor(stock_code)
    # get_foreign_net_trading_summary(market) #0000(전체), 1001(코스피), 2001(코스닥)
    # get_program_trade_summary_by_time(stock_code, market)
    # get_summarize_foreign_net_estimates(stock_code)