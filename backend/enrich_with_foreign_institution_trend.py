import pandas as pd
CACHE_DIR = "/Users/hyungseoklee/Documents/Leonardo/backend/cache"

from get_total_data_for_candidates import get_foreign_institution_trend, get_foreign_net_trend
from tqdm import tqdm
from loguru import logger
import json
import time
from utils import KoreaInvestAPI, KoreaInvestEnv
from settings import cfg

# Load DEBUG setting
with open(f"{CACHE_DIR}/settings.json") as f:
    settings = json.load(f)
DEBUG = settings.get("DEBUG", "False") == "True"

def enrich_with_foreign_institution_trend(df_result):

    frgn_qty_list = []
    orgn_qty_list = []

    # Initialize columns with NaN
    df_result['외국인'] = pd.NA
    df_result['기관'] = pd.NA

    for _, row in tqdm(df_result.iterrows(), total=len(df_result), desc="🧩 외국인/기관 추정 데이터 추가 중"):
        code = str(row['Code']).zfill(6)
        if DEBUG: logger.debug(f"📨 종목 코드 변환 및 호출: {code}")

        time.sleep(0.5)

        try:
            df_trend = get_foreign_institution_trend(code)
            if DEBUG and not df_trend.empty:
                logger.debug(f"🧾 {code} 외국인/기관 추정 전체 데이터프레임:\n{df_trend}")
                logger.debug(f"📑 {code} 컬럼 목록: {df_trend.columns.tolist()}")
            if df_trend.empty:
                frgn_qty_list.append(None)
                orgn_qty_list.append(None)
                continue
            latest_row = df_trend[df_trend["bsop_hour_gb"] == df_trend["bsop_hour_gb"].max()].iloc[0]
            logger.debug(f"📥 원시 외국인 수치: {latest_row['frgn_fake_ntby_qty']}")
            logger.debug(f"🏛️ 원시 기관 수치: {latest_row['orgn_fake_ntby_qty']}")
            # Ensure string-to-int conversion with comma removal, and round to int (no decimals)
            frgn_qty_list.append(round(int(str(latest_row['frgn_fake_ntby_qty']).replace(",", ""))))
            orgn_qty_list.append(round(int(str(latest_row['orgn_fake_ntby_qty']).replace(",", ""))))

        except Exception as e:
            if DEBUG: logger.warning(f"❌ {str(code)} 데이터 처리 중 오류 발생: {e}")
            frgn_qty_list.append(None)
            orgn_qty_list.append(None)

    logger.debug(f"📏 df_result 길이: {len(df_result)}")
    logger.debug(f"🧮 외국인 수집 리스트 길이: {len(frgn_qty_list)}")
    logger.debug(f"🏛️ 기관 수집 리스트 길이: {len(orgn_qty_list)}")
    df_result["Code"] = df_result["Code"].apply(lambda x: str(x).zfill(6))
    for i, idx in enumerate(df_result.head(10).index):
        df_result.at[idx, '외국인'] = frgn_qty_list[i]
        df_result.at[idx, '기관'] = orgn_qty_list[i]
        logger.debug(f"📊 저장된 외국인: {frgn_qty_list[i]}, 저장된 기관: {orgn_qty_list[i]}")
    df_result["외국인"] = df_result["외국인"].fillna(0).astype(int)
    df_result["기관"] = df_result["기관"].fillna(0).astype(int)
    return df_result


# 외국계 순매수 데이터 추가 함수
def enrich_with_foreign_net_trend(df_result):
    codes = df_result["Code"].astype(str).tolist()
    logger.debug(f"📥 get_foreign_net_trend 호출 값: {codes} / 타입: {type(codes)}")
    foreign_net_data = []
    for code in tqdm(codes, desc="🔄 외국계 순매수 수집 중"):
        try:
            logger.debug(f"🚀 외국계 순매수 데이터 요청 중 - 종목코드: {code}")
            result = get_foreign_net_trend(code)
            logger.debug(f"📦 {code} 외국계 전체 응답 데이터: {result}")
            acml_vol = 0
            if isinstance(result, dict) and "output" in result and isinstance(result["output"], list) and result["output"]:
                first_entry = result["output"][0]
                acml_vol = int(first_entry.get("acml_vol", "0").replace(",", ""))
                logger.debug(f"📊 {code} 외국계 누적 거래량(acml_vol): {acml_vol}")
            else:
                logger.warning(f"⚠️ {code}의 외국계 응답에서 'acml_vol' 추출 실패 - result: {result}")

            result_df = pd.DataFrame([{"Code": code, "외국계": acml_vol}])
            foreign_net_data.append(result_df)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"❌ {code} 외국계 순매수 처리 중 오류: {e}")

    foreign_net_df = pd.concat(foreign_net_data) if foreign_net_data else pd.DataFrame()

    if not foreign_net_df.empty:
        if "외국계" not in foreign_net_df.columns:
            logger.error("❌ foreign_net_df에 '외국계' 컬럼이 없습니다. 응답 데이터 확인 필요")
            logger.debug(f"📄 foreign_net_df 내용:\n{foreign_net_df}")
        else:
            logger.debug(f"🧮 병합 전 외국계 데이터 전체 preview:\n{foreign_net_df.head()}")
            logger.debug(f"🧾 foreign_net_df columns: {foreign_net_df.columns.tolist()}")
    else:
        logger.warning("❌ 외국계 순매수 데이터가 비어 있습니다.")
        logger.debug(f"📜 수집된 foreign_net_data 목록 (빈 경우 확인): {foreign_net_data}")
        df_result["외국계"] = 0
        return df_result

    df_result = df_result.merge(foreign_net_df, how="left", on="Code")

    if "외국계_x" in df_result.columns:
        df_result["외국계"] = df_result["외국계_x"].fillna(0).astype(int)
        df_result = df_result.drop(columns=["외국계_x", "외국계_y"], errors="ignore")
    else:
        logger.error("❌ '외국계_x' 컬럼이 병합 결과에 존재하지 않습니다. 기본값으로 0 삽입")
        df_result["외국계"] = 0

    return df_result





if __name__ == "__main__":

    ORIGINAL_PATH = f"{CACHE_DIR}/high52.json"
    OUTPUT_PATH = f"{CACHE_DIR}/high52_with_trend.json"
    try:
        df = pd.read_json(ORIGINAL_PATH)
        df = enrich_with_foreign_institution_trend(df)
        df = enrich_with_foreign_net_trend(df)  # ✅ 외국계 순매수 정보 추가
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 외국인/기관/외국계 정보가 추가된 high52_with_trend.json 저장 완료")
    except Exception as e:
        logger.error(f"❌ high52_with_trend.json 처리 중 오류 발생: {e}")