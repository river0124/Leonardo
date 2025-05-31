import os
import json
import FinanceDataReader as fdr
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc
from datetime import datetime
from tqdm import tqdm
import multiprocessing
import pandas as pd

HOLIDAYS_PATH = '/Users/hyungseoklee/Documents/Leonardo/backend/cache/holidays.csv'
df_holidays = pd.read_csv(HOLIDAYS_PATH, dtype=str)
df_holidays['date'] = pd.to_datetime(df_holidays['날짜'], format='%Y%m%d')
holidays = df_holidays['date'].dt.date.tolist()

TEST_MODE = False  # 테스트 시 True로 설정
TEST_CODE = '005930'  # 삼성전자

IMAGE_WINDOW_DAYS = 60
HIGH_LOOKBACK_DAYS = 252

# 저장 경로 설정
POS_DIR = '/Volumes/riverpic/leonardo_ai/52WeekHigh/data/images/positive'
NEG_DIR = '/Volumes/riverpic/leonardo_ai/52WeekHigh/data/images/negative'

def ensure_dirs():
    os.makedirs(POS_DIR, exist_ok=True)
    os.makedirs(NEG_DIR, exist_ok=True)

def is_52week_high(df, index):
    past_window = df.iloc[index-HIGH_LOOKBACK_DAYS:index]
    if len(past_window) < HIGH_LOOKBACK_DAYS:
        return False
    high_lookback = past_window['High'].max()
    return df.iloc[index]['Close'] > high_lookback

def save_chart_image(df, idx, code, label_dir):
    filename = f"{code}_{df.index[idx].date()}.png"
    filepath = os.path.join(label_dir, filename)
    if os.path.exists(filepath):
        return

    window = df.iloc[idx-(IMAGE_WINDOW_DAYS+1):idx+1].copy()
    if len(window) < IMAGE_WINDOW_DAYS + 1:
        return

    window['X'] = range(len(window))
    ohlc = window[['X', 'Open', 'High', 'Low', 'Close']]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5.12, 5.12), dpi=100,
                                   gridspec_kw={'height_ratios': [3, 1]}, sharex=True)

    # 캔들 차트
    candlestick_ohlc(ax1, ohlc.values, width=0.6, colorup='red', colordown='blue')
    ax1.axis('off')

    # 거래량 차트
    volume_colors = ['red' if c >= o else 'blue' for c, o in zip(window['Close'], window['Open'])]
    ax2.bar(window['X'], window['Volume'], color=volume_colors, width=0.6)
    ax2.axis('off')

    # Save label JSON
    json_data = {
        'filename': os.path.basename(filepath),
        'code': code,
        'date': str(df.index[idx].date()),
        'is_breakout': int(label_dir == POS_DIR),
        'is_uptrend': int(df['Close'].iloc[idx] > df['Close'].iloc[idx - 20]),
        'vol_spike': int(df['Volume'].iloc[idx] > df['Volume'].iloc[idx - 20:idx].mean() * 3)
    }
    json_dir = os.path.join(label_dir, 'json')
    os.makedirs(json_dir, exist_ok=True)
    json_path = os.path.join(json_dir, os.path.basename(filepath).replace('.png', '.json'))
    with open(json_path, 'w') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    plt.tight_layout()
    plt.savefig(filepath, bbox_inches=None, pad_inches=0)
    plt.close()

def generate_images_for_stock(code):
    import glob

    try:
        df = fdr.DataReader(code)
        df = df[~df.index.floor('D').isin(pd.to_datetime(holidays))]
        df = df.dropna()
        if len(df) < 300:
            return

        # 가격 변동이 거의 없는 종목 필터링 (예: 정지 종목)
        price_range = df['Close'].iloc[-30:].max() - df['Close'].iloc[-30:].min()
        mean_price = df['Close'].iloc[-30:].mean()
        if mean_price == 0 or price_range / mean_price < 0.005:
            return  # 최근 30일간 변동성이 0.5% 미만인 경우 제외

        # 거래정지 또는 이상 데이터 필터링
        daily_gap = df.index.to_series().diff().dt.days
        if daily_gap.median() > 2:
            return

        # 파일 이름을 기준으로 생성된 날짜 리스트 확보
        existing_files = set()
        for d in [POS_DIR, NEG_DIR]:
            existing_files.update(os.path.basename(f) for f in glob.glob(os.path.join(d, f"{code}_*.png")))

        for i in range(IMAGE_WINDOW_DAYS + 120, len(df) - 5):
            date_str = str(df.index[i].date())
            filename = f"{code}_{date_str}.png"
            if filename in existing_files:
                continue
            try:
                label_dir = POS_DIR if is_52week_high(df, i) else NEG_DIR
                save_chart_image(df, i, code, label_dir)
            except Exception as e:
                print(f"[{code}] Error at index {i}: {e}")
    except Exception as e:
        print(f"❌ {code} 추복 실패: {e}")

def main():
    ensure_dirs()
    if TEST_MODE:
        codes = [TEST_CODE]
    else:
        stock_list = fdr.StockListing('KRX')
        codes = stock_list['Code'].tolist()

    cpu_count = max(1, int(multiprocessing.cpu_count() * 0.8))
    with multiprocessing.Pool(processes=cpu_count) as pool:
        list(tqdm(pool.imap_unordered(generate_images_for_stock, codes), total=len(codes)))

if __name__ == "__main__":
    main()
