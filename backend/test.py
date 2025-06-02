from pykrx.stock import get_market_cap_by_ticker
from pykrx.stock import get_nearest_business_day_in_a_week
from datetime import datetime

# 날짜 설정
today = datetime.today().strftime("%Y%m%d")
valid_date = get_nearest_business_day_in_a_week(today)

# 시가총액 DataFrame
cap_df = get_market_cap_by_ticker(valid_date)

# 예시: 060310 (3S)
print(cap_df)
print(cap_df.loc["060310"])  # 또는 cap_df.at["060310", "시가총액"]