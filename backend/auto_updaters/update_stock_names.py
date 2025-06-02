import FinanceDataReader as fdr
import os, sys
from pykrx import stock  # ✅ pykrx 사용

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from slack_notifier import post_to_slack  # ✅ 슬랙 전송 모듈

def main():
    try:
        print("📥 최신 종목 목록을 가져오는 중...")
        df = fdr.StockListing('KRX')[['Name', 'Code', 'Market']]
        df["Sector1"] = ""
        df["Sector2"] = ""
        df = df[df["Market"] != "KONEX"]
        df["Code"] = df["Code"].apply(lambda x: str(x).zfill(6))

        # 우선주 및 스팩 제외 (정규표현식, warning 방지)
        df = df[~df["Name"].str.contains(r"(?:[0-9]*우(?:B)?|우선주|스팩)", case=False, regex=True)]  # 우선주 및 스팩 제외

        import datetime
        from pykrx.stock import get_nearest_business_day_in_a_week

        today = datetime.datetime.today().strftime("%Y%m%d")
        valid_date = get_nearest_business_day_in_a_week(today)

        # 코스피, 코스닥 시총 병합
        kospi_cap = stock.get_market_cap_by_ticker(valid_date, market="KOSPI")[["시가총액"]]
        kosdaq_cap = stock.get_market_cap_by_ticker(valid_date, market="KOSDAQ")[["시가총액"]]
        kospi_cap.index = kospi_cap.index.map(lambda x: str(x).zfill(6))
        kosdaq_cap.index = kosdaq_cap.index.map(lambda x: str(x).zfill(6))
        cap = kospi_cap.combine_first(kosdaq_cap)
        cap.index.name = "Code"
        cap = cap.reset_index().rename(columns={"시가총액": "MarketCap"})
        cap["MarketCap"] = cap["MarketCap"].astype(float)

        # 종목코드 기준으로 merge
        df = df.merge(cap, on="Code", how="left")

        # KOSPI200, KOSDAQ150 종목 코드 리스트
        kospi200_codes = set(stock.get_index_portfolio_deposit_file("1028"))
        kosdaq150_codes = set(stock.get_index_portfolio_deposit_file("3011"))

        # 컬럼 추가
        df["Index"] = df["Code"].apply(lambda x: "KOSPI200" if x in kospi200_codes else ("KOSDAQ150" if x in kosdaq150_codes else ""))

        # df already includes 'Market', no need to merge again

        # ⬇️ 가나다 순으로 정렬 및 마켓 + 시총 정보 포함
        df = df.sort_values(by='Name')

        print(f"📊 총 종목 수: {len(df)}")
        sector_counts = df['Sector1'].value_counts(dropna=False)
        print("📌 섹터별 종목 수:")
        print(sector_counts)
        print(f"🔢 총 섹터 수: {df['Sector1'].nunique(dropna=True)} (NaN 제외)")

        # 저장 경로
        leo_project_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
        sector_counts = df['Sector1'].value_counts(dropna=False)
        print("📌 섹터별 종목 수:")
        print(sector_counts)
        print(f"🔢 총 섹터 수: {df['Sector1'].nunique(dropna=True)} (NaN 제외)")
        df[["Name", "Code", "Market", "MarketCap", "Index", "Sector1", "Sector2"]].to_csv(leo_project_path, index=False, encoding="utf-8-sig")

        print(f"✅ stock_list.csv 저장 완료! (경로: {leo_project_path})")

        # ✅ 슬랙 알림
        post_to_slack("✅ 종목 리스트(stock_list.csv) 업데이트 완료")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        post_to_slack(f"❌ 종목 리스트 업데이트 실패: {e}")

if __name__ == "__main__":
    main()