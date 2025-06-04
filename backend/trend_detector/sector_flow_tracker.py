import pandas as pd
from datetime import datetime, timedelta

def get_dual_period_hot_sectors(
    price_data_path: str = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/daily_price.csv",
    metadata_path: str = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
) -> dict:
    """
    20일 및 60일 상승률 기준으로 '핫한' 섹터를 추출

    Parameters:
    - price_data_path: 종목별 일별 시세 데이터 CSV 경로
    - metadata_path: stock_metadata.csv 경로

    Returns:
    - {
        "20일": 상위 섹터 리스트,
        "60일": 상위 섹터 리스트,
        "공통": 두 구간 모두 포함된 섹터 리스트
      }
    """
    def get_sector_performance(days: int):
        cutoff = datetime.now() - timedelta(days=days)
        recent = price_df[price_df["Date"] >= cutoff]
        returns = recent.groupby("Code")["Close"].agg(["first", "last"])
        returns["Return"] = (returns["last"] - returns["first"]) / returns["first"]
        returns = returns.reset_index().merge(metadata_df[["Code", "Sector1"]], on="Code", how="left")
        returns = returns.dropna(subset=["Sector1"])
        sector_perf = returns.groupby("Sector1")["Return"].mean().sort_values(ascending=False)
        return sector_perf.head(5).index.tolist()

    # Load data
    metadata_df = pd.read_csv(metadata_path, dtype={"Code": str})
    metadata_df = metadata_df.dropna(subset=["Sector1"])
    price_df = pd.read_csv(price_data_path, dtype={"Code": str}, parse_dates=["Date"])

    top_20 = get_sector_performance(20)
    top_60 = get_sector_performance(60)
    common = list(set(top_20) & set(top_60))

    return {
        "20일": top_20,
        "60일": top_60,
        "공통": common
    }

# 예시 사용법:
hot_sectors = get_dual_period_hot_sectors()
print("20일 핫섹터:", hot_sectors["20일"])
print("60일 핫섹터:", hot_sectors["60일"])
# print("공통 섹터:", hot_sectors["공통"])