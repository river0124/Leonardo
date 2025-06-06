import FinanceDataReader as fdr
import os, sys
from pykrx import stock  # ✅ pykrx 사용
import pandas as pd
import datetime
from pykrx.stock import get_nearest_business_day_in_a_week
from tqdm import tqdm
from loguru import logger
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from slack_notifier import post_to_slack  # ✅ 슬랙 전송 모듈

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, '..', '.env')
# .env 파일 로드
load_dotenv()

# 환경변수에서 경로 읽기, 없으면 기본값으로 로컬 경로 지정
CACHE_DIR = os.getenv('CACHE_DIR', '/Users/hyungseoklee/Documents/Leonardo/backend/cache')

HOLIDAY_PATH = os.path.join(CACHE_DIR, 'holidays.csv')
STOCK_LIST_PATH = os.path.join(CACHE_DIR, 'stock_list.csv')

def get_recent_trading_dates(n_days=10):
    """
    최근 거래일 계산 함수
    - 주말(토, 일) 및 공휴일(csv에 정의된)을 제외한 n_days만큼 과거 거래일 리스트 중 가장 오래된 날짜 반환
    """
    today = datetime.date.today()
    holidays_df = pd.read_csv(HOLIDAY_PATH)
    holidays = set(pd.to_datetime(holidays_df["날짜"], format="%Y%m%d").dt.date)
    trading_days = []
    delta = datetime.timedelta(days=1)
    check_day = today
    # 주말(토,일) 및 공휴일을 제외하고 거래일만 누적
    while len(trading_days) < n_days:
        if check_day.weekday() < 5 and check_day not in holidays:
            trading_days.append(check_day)
        check_day -= delta
    # 가장 오래된 거래일 반환
    return trading_days[-1]

def has_price_movement(code):
    try:
        start_date = get_recent_trading_dates(5)
        hist = fdr.DataReader(code, start_date)
        if len(hist) < 5:
            return False
        return hist['Close'].nunique() > 1
    except:
        return False

def main():
    try:
        # 1. 종목 리스트 불러오기
        logger.info("📥 최신 종목 목록을 가져오는 중...")
        df = fdr.StockListing('KRX')[['Name', 'Code', 'Market']]
        df = df[df["Market"] != "KONEX"]

        # 2. 최근 5거래일간 가격 변동이 없는 종목 제거
        tqdm.pandas(desc="⏳ 가격 변동 필터링 진행 중")
        df["has_movement"] = df["Code"].progress_apply(has_price_movement)
        excluded_df = df[~df["has_movement"]]
        print("🧹 최근 5거래일 동안 가격이 변하지 않은 종목:")
        print(excluded_df[["Name", "Code"]])
        df = df[df["has_movement"]]
        df = df.drop(columns=["has_movement"])

        # 3. 종목 코드 및 마켓 정리
        df["Market"] = df["Market"].replace("KOSDAQ GLOBAL", "KOSDAQ")
        df["Code"] = df["Code"].apply(lambda x: str(x).zfill(6))

        # 4. 우선주 및 스팩 제외 (정규표현식)
        df = df[~df["Name"].str.contains(r"(?:[0-9]*우(?:B)?|우선주|스팩)", case=False, regex=True)]

        # 5. 시가총액 정보 병합
        today = datetime.datetime.today().strftime("%Y%m%d")
        valid_date = get_nearest_business_day_in_a_week(today)
        kospi_cap = stock.get_market_cap_by_ticker(valid_date, market="KOSPI")[["시가총액"]]
        kosdaq_cap = stock.get_market_cap_by_ticker(valid_date, market="KOSDAQ")[["시가총액"]]
        for cap_df in (kospi_cap, kosdaq_cap):
            cap_df.index = cap_df.index.map(lambda x: str(x).zfill(6))
        cap = kospi_cap.combine_first(kosdaq_cap).reset_index()
        cap.columns = ["Code", "MarketCap"]
        cap["MarketCap"] = cap["MarketCap"].astype("Int64")
        df = df.merge(cap, on="Code", how="left")

        # 6. KOSPI200, KOSDAQ150 포함 여부 체크
        kospi200_codes = set(stock.get_index_portfolio_deposit_file("1028"))
        kosdaq150_codes = set(stock.get_index_portfolio_deposit_file("3011"))
        df["Index"] = df["Code"].apply(lambda x: "KOSPI200" if x in kospi200_codes else ("KOSDAQ150" if x in kosdaq150_codes else ""))

        # 7. 정렬 및 저장
        df = df.sort_values(by='Name')
        logger.info(f"📊 총 종목 수: {len(df)}")
        logger.info(f"KOSDAQ150 포함 종목 수: {(df['Code'].isin(kosdaq150_codes)).sum()}")
        df[["Name", "Code", "Market", "MarketCap", "Index"]].to_csv(STOCK_LIST_PATH, index=False, encoding="utf-8-sig")
        logger.info(f"✅ stock_list.csv 저장 완료! (경로: {STOCK_LIST_PATH})")

        # 8. 슬랙 알림
        post_to_slack("✅ 종목 리스트 업데이트 완료")

    except Exception as e:
        logger.info(f"❌ 오류 발생: {e}")
        post_to_slack(f"❌ 종목 리스트 업데이트 실패: {e}")

if __name__ == "__main__":
    main()