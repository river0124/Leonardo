import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any
from collections import Counter
from tqdm import tqdm

# --- 상수 정의 ---
# 기간 설정 (일 수) - 범위로 변경
PERIODS: Dict[str, Tuple[int, int]] = {
    "초단기": (5, 10),
    "단기": (10, 10),
    "중기": (20, 60),
    "장기": (120, 365)
}

# 인덱스 코드
INDEX_CODES: Dict[str, str] = {
    'KOSPI': 'KS11',
    'KOSDAQ': 'KQ11'
}

# 추세 단계 정의
STAGE_DOWNTREND = 1
STAGE_CONSOLIDATION = 2
STAGE_REVERSAL_ATTEMPT = 3
STAGE_UPTREND = 4
STAGE_OVERHEAT = 5
# STAGE_UNDETERMINED = 0 # 데이터 부족 등으로 결정 불가 시 (현재는 STAGE_CONSOLIDATION으로 처리)

# 추세 단계 설명
STAGE_DESCRIPTIONS: Dict[int, str] = {
    STAGE_DOWNTREND: "하락 추세 (이동평균 하회, 하방 추세)",
    STAGE_CONSOLIDATION: "바닥 다지기 / 횡보 구간",
    STAGE_REVERSAL_ATTEMPT: "추세 전환 시도 (이동평균 위로 돌파 시도)",
    STAGE_UPTREND: "상승 추세 형성 (이동평균 위, 상승 진행)",
    STAGE_OVERHEAT: "과열 구간 (고점 대비 이격 확대, 변동성 증가)",
    # STAGE_UNDETERMINED: "추세 판단 불가 (데이터 부족)"
}

# classify_trend_stage 함수 내 임계값 상수
MA_WINDOW = 20
# MA20 기울기가 이 값 미만이면 횡보로 간주 (매우 작은 절대값, KOSPI 포인트 기준)
# 주가 스케일에 따라 조정 필요. 예를 들어, KOSPI 2700 기준 0.01은 극도로 평평함을 의미.
# 좀 더 의미있는 값 (예: 0.5 또는 1.0) 또는 주가 대비 비율로 변경 고려.
SLOPE_THRESHOLD_FOR_FLAT = 0.01
# 주가가 MA20 대비 이 비율(%) 미만으로 차이나면 횡보 간주
PRICE_MA20_DIFF_PERCENT_FOR_FLAT = 0.01
# 변동성( (고가-저가)/종가 )이 이 값 초과 시 과열 간주
VOLATILITY_THRESHOLD_FOR_OVERHEAT = 0.05
# 주가가 MA20 대비 이 배율 초과 시 과열 간주 (예: MA20의 10% 위)
PRICE_MA20_MULTIPLIER_FOR_OVERHEAT = 1.1


def classify_trend_stage(df: pd.DataFrame) -> int:
    """
    주어진 데이터프레임을 기반으로 추세 단계를 1~5단계로 분류합니다.

    Args:
        df: 'Open', 'High', 'Low', 'Close' 컬럼을 포함하는 Pandas DataFrame.

    Returns:
        추세 단계를 나타내는 정수 (1-5). 데이터 부족 시 STAGE_CONSOLIDATION 반환.
    """
    if df.empty or len(df) < MA_WINDOW + 1:  # MA 및 slope 계산에 필요한 최소 데이터 + 이전 날짜 접근
        # logger.warning("데이터 부족으로 추세 판단 불가, 기본값 반환") # 로깅 라이브러리 사용 시
        return STAGE_CONSOLIDATION

    df_copy = df.copy()
    df_copy['MA20'] = df_copy['Close'].rolling(window=MA_WINDOW).mean()
    df_copy['MA20_Slope'] = df_copy['MA20'].diff()
    # 일일 변동성: (고가 - 저가) / 종가
    df_copy['Volatility'] = (df_copy['High'] - df_copy['Low']) / df_copy['Close']

    # 마지막 데이터 포인트에서 NaN 값 확인
    last_row = df_copy.iloc[-1]
    if pd.isna(last_row['Close']) or \
            pd.isna(last_row['MA20']) or \
            pd.isna(last_row['MA20_Slope']) or \
            pd.isna(last_row['Volatility']):
        # logger.warning("최신 데이터의 지표 계산 불가, 기본값 반환")
        return STAGE_CONSOLIDATION

    # Stage 3 (추세 전환 시도)는 이전 날짜 데이터 필요
    if len(df_copy) < MA_WINDOW + 2:  # MA계산 + diff + 이전날짜 접근
        # logger.warning("추세 전환 시도 판단 위한 데이터 부족, 해당 단계 건너뜀")
        can_check_stage_3 = False
    else:
        prev_row = df_copy.iloc[-2]
        if pd.isna(prev_row['Close']) or pd.isna(prev_row['MA20']):
            # logger.warning("이전 날짜 데이터의 지표 계산 불가 (Stage 3), 해당 단계 건너뜀")
            can_check_stage_3 = False
        else:
            can_check_stage_3 = True
            prev_close = prev_row['Close']
            prev_ma20 = prev_row['MA20']

    current_close = last_row['Close']
    current_ma20 = last_row['MA20']
    current_ma20_slope = last_row['MA20_Slope']
    current_volatility = last_row['Volatility']

    # 1단계: 하락 추세
    if current_close < current_ma20 and current_ma20_slope < 0:
        return STAGE_DOWNTREND

    # 상승 관련 추세 확인 (MA20 위 & MA20 상승)
    if current_close > current_ma20 and current_ma20_slope > 0:
        # 5단계: 과열 구간 (상승 추세 중 특정 조건 만족 시)
        if current_volatility > VOLATILITY_THRESHOLD_FOR_OVERHEAT and \
                current_close > current_ma20 * PRICE_MA20_MULTIPLIER_FOR_OVERHEAT:
            return STAGE_OVERHEAT

        # 3단계: 추세 전환 시도 (MA20 골든크로스 직후)
        if can_check_stage_3 and prev_close <= prev_ma20:
            return STAGE_REVERSAL_ATTEMPT

        # 4단계: 상승 추세 형성 (일반적인 상승 추세)
        return STAGE_UPTREND

    # 2단계: 바닥 다지기 (횡보)
    # MA20 기울기가 매우 작고, 현재가가 MA20에 매우 근접
    if abs(current_ma20_slope) < SLOPE_THRESHOLD_FOR_FLAT and \
            abs(current_close - current_ma20) < (PRICE_MA20_DIFF_PERCENT_FOR_FLAT * current_close):
        return STAGE_CONSOLIDATION

    # 위 조건에 해당하지 않으면 기본적으로 횡보(2단계)로 간주
    return STAGE_CONSOLIDATION


def analyze_index_trend(kospi_df: pd.DataFrame, kosdaq_df: pd.DataFrame) -> Dict[str, int]:
    """KOSPI와 KOSDAQ 데이터프레임을 받아 각 지수의 추세 단계를 분석합니다."""
    return {
        'KOSPI_Stage': classify_trend_stage(kospi_df),
        'KOSDAQ_Stage': classify_trend_stage(kosdaq_df)
    }


def analyze_and_print_index_trends():
    """KOSPI/KOSDAQ 지수의 단기, 중기, 장기 추세 단계를 분석하고 출력합니다."""
    today = datetime.today()
    print("--- 지수 추세 분석 ---")
    for label, days in PERIODS.items():
        start_day, end_day = PERIODS[label]
        start_date_dt = today - timedelta(days=end_day)
        start_date_str = start_date_dt.strftime('%Y-%m-%d')
        print(f"\n기간: {label} (최근 {start_day}~{end_day}일, 시작일: {start_date_str})")
        try:
            kospi_df = fdr.DataReader(INDEX_CODES['KOSPI'], start_date_str, end=today.strftime('%Y-%m-%d'))
            kosdaq_df = fdr.DataReader(INDEX_CODES['KOSDAQ'], start_date_str, end=today.strftime('%Y-%m-%d'))

            if kospi_df.empty or kosdaq_df.empty:
                print(f"  ⚠️ {label} 데이터 조회 실패 또는 데이터 없음.")
                continue

            result = analyze_index_trend(kospi_df, kosdaq_df)
            print(
                f"  📊 KOSPI 추세 단계 ({result['KOSPI_Stage']}): {STAGE_DESCRIPTIONS.get(result['KOSPI_Stage'], '알 수 없음')}")
            print(
                f"  📊 KOSDAQ 추세 단계 ({result['KOSDAQ_Stage']}): {STAGE_DESCRIPTIONS.get(result['KOSDAQ_Stage'], '알 수 없음')}")

        except Exception as e:
            print(f"  ❌ {label} 기간 데이터 분석 중 오류 발생: {e}")


def get_trend_scores() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    KOSPI/KOSDAQ의 단기, 중기, 장기 추세 단계를 점수(투표, 평균, 일관성)로 반환합니다.
    상승 추세일수록 높은 점수를 가집니다.
    """
    today = datetime.today()
    scores: Dict[str, Dict[str, Dict[str, Any]]] = {index_name: {} for index_name in INDEX_CODES.keys()}

    for index_name, code in tqdm(list(INDEX_CODES.items()), desc="📈 인덱스 분석 진행 중", total=len(INDEX_CODES), position=0, leave=True):
        for period_label, (start_day, end_day) in tqdm(list(PERIODS.items()), desc=f"{index_name} 기간 분석", total=len(PERIODS), position=1, leave=False):
            stages = []
            for day in range(start_day, end_day + 1):
                start_date_dt = today - timedelta(days=day)
                start_date_str = start_date_dt.strftime('%Y-%m-%d')
                try:
                    df = fdr.DataReader(code, start_date_str, end=today.strftime('%Y-%m-%d'))
                    if not df.empty:
                        stage = classify_trend_stage(df)
                        stages.append(stage)
                except Exception:
                    # 오류 발생 시 해당 일자는 무시
                    pass
            if stages:
                vote = Counter(stages).most_common(1)[0][0]
                mean = round(sum(stages) / len(stages), 2)
                consistent = int(len(set(stages)) == 1)
            else:
                vote = STAGE_CONSOLIDATION
                mean = float(STAGE_CONSOLIDATION)
                consistent = 0

            scores[index_name][period_label] = {
                "vote": vote,
                "mean": mean,
                "consistent": consistent
            }
    print(f"✅ 트렌드 분석 점수 요약: {scores}")
    return scores

def print_trend_scores(trend_scores: Dict[str, Dict[str, Dict[str, Any]]]):
    print("\n📊 상세 추세 점수 및 설명")
    print("=" * 80)
    print(f"{'지수':<10} {'기간':<8} {'투표':<5} {'평균':<6} {'일관성':<5} {'설명'}")
    print("-" * 80)
    for index_name, period_info in trend_scores.items():
        for period_label, info in period_info.items():
            vote = info["vote"]
            mean = info["mean"]
            consistent = "✅" if info["consistent"] else "❌"
            desc = STAGE_DESCRIPTIONS.get(vote, "알 수 없음")
            print(f"{index_name:<10} {period_label:<8} {vote:<5} {mean:<6} {consistent:<5} {desc}")
    print("=" * 80)

# Later in the file, after get_trend_scores() call
if __name__ == "__main__":
    analyze_and_print_index_trends()
    print("\n--- 지수 추세 점수 ---")
    trend_scores = get_trend_scores()
    print_trend_scores(trend_scores)
