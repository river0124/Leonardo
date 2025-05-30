def find_52week_high_candidates():
    import FinanceDataReader as fdr
    from tqdm import tqdm
    import pandas as pd
    from datetime import datetime, timedelta
    from trend_analyzer import get_trend_scores

    trend_scores = get_trend_scores()  # {'KOSPI': {'short': 4, ...}, 'KOSDAQ': {'short': 2, ...}}

    sum_kospi = sum(trend_scores.get("KOSPI", {}).values())
    sum_kosdaq = sum(trend_scores.get("KOSDAQ", {}).values())
    preferred_market = "KOSPI" if sum_kospi > sum_kosdaq else "KOSDAQ"

    stock_list = fdr.StockListing('KRX')
    stock_list['Market'] = stock_list['Code'].apply(lambda x: 'KOSDAQ' if x.startswith('1') else 'KOSPI')
    stock_list = stock_list[~stock_list['Name'].str.contains('관리|정지|스팩|전환|우$|우[A-Z]?$|우선', regex=True, na=False)]
    stock_list['Close'] = pd.to_numeric(stock_list['Close'], errors='coerce')
    stock_list = stock_list[stock_list['Close'] > 1000]

    end = datetime.today()
    start = end - timedelta(days=365)

    excluded_names = []
    results = []

    for _, row in tqdm(stock_list.iterrows(), total=stock_list.shape[0], desc="Processing"):
        code = row['Code']
        name = row['Name']

        df = fdr.DataReader(code, start, end)
        if df.empty or len(df) < 10:
            excluded_names.append(name)
            continue

        recent = df.tail(7)
        if (recent['Volume'] == 0).all() or recent[['Open', 'High', 'Low', 'Close']].nunique().eq(1).all():
            excluded_names.append(name)
            continue

        # 윗꼬리/장대음봉 제외 조건
        recent_candle = df.iloc[-1]
        upper_shadow = recent_candle['High'] - max(recent_candle['Close'], recent_candle['Open'])
        candle_body = abs(recent_candle['Close'] - recent_candle['Open'])

        # 제외 조건: 윗꼬리가 몸통의 2배 이상이거나, 장대 음봉(전일 대비 -5% 이상)
        long_upper_shadow = upper_shadow > candle_body * 2
        big_bearish_candle = recent_candle['Close'] < recent_candle['Open'] and \
                             (recent_candle['Close'] / recent_candle['Open']) < 0.95

        if long_upper_shadow or big_bearish_candle:
            excluded_names.append(name)
            continue

        try:
            high_before_today = df['High'].iloc[:-1].max()
            current_price = df['Close'].iloc[-1]

            # 추가 조건: 거래량 증가 확인
            avg_volume = df['Volume'].rolling(window=20).mean().iloc[-2]
            current_volume = df['Volume'].iloc[-1]
            is_volume_spike = current_volume > avg_volume * 1.8

            # 추가 조건: 20일 이동 평균 상승 추세
            ma20 = df['Close'].rolling(window=20).mean()
            is_ma20_up = ma20.iloc[-1] > ma20.iloc[-2] * 1.02

            # 추가 조건: MACD > Signal
            exp1 = df['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df['Close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            is_macd_bullish = macd.iloc[-1] > signal.iloc[-1] * 1.02

            # 52주 고가 (252일 고가) 계산 (마지막 날 제외, NaN 방지)
            high_52week = df['High'].iloc[:-1].dropna().max()

            # 최근 3~5일간 횡보 구간 확인 (마지막 5일 고가와 저가의 편차가 작을 것)
            last_5days = df.iloc[-6:-1]
            consolidation_range = last_5days['High'].max() - last_5days['Low'].min()

            market = 'KOSDAQ' if code.startswith('1') else 'KOSPI'
            market_score_bias = 0

            # 세분화된 추세 가중치: 단기, 중기, 장기 각각에 따라 점수 보정
            if trend_scores[market]['단기'] >= 4:
                market_score_bias += 0.5
            if trend_scores[market]['중기'] >= 4:
                market_score_bias += 0.5
            if trend_scores[market]['장기'] >= 4:
                market_score_bias += 0.5

            score = 0
            score += current_price > high_52week * 1.04  # 52주 고가 대비 4% 이상 돌파한 경우 (더욱 강화)
            score += is_volume_spike and current_volume > avg_volume * 4.0  # 거래량 조건 더욱 더 강화
            score += is_ma20_up and ma20.iloc[-1] > ma20.iloc[-5] * 1.15  # 이동 평균 상승폭 최고 강화
            score += is_macd_bullish and macd.iloc[-1] > macd.iloc[-5]
            score += consolidation_range < high_52week * 0.006  # 횡보 구간 극도로 타이트하게 강화
            score += market_score_bias  # 추세 기반 가중치 적용

            if score >= 3:
                results.append({
                    'Code': code,
                    'Name': name,
                    'CurrentPrice': current_price,
                    'High52Week': high_52week,
                    'Ratio': round((current_price / high_52week) * 100, 2) if pd.notna(high_52week) and high_52week != 0 else None,
                    'Score': round(score, 2),
                })

        except Exception as e:
            print(f"[{code}] {name}: Error -> {e}")

    df_result = pd.DataFrame(results, columns=['Code', 'Name', 'CurrentPrice', 'High52Week', 'Ratio', 'Score'])
    if not df_result.empty:
        df_result = df_result.sort_values(by='Score', ascending=False)

    return df_result