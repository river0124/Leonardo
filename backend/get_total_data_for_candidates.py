from utils_backup import KoreaInvestAPI, KoreaInvestEnv
from settings import cfg
import time
import json
import pandas as pd
from loguru import logger

CACHE_DIR = "/Users/hyungseoklee/Documents/Leonardo/backend/cache"

with open(f"{CACHE_DIR}/settings.json") as f:
    settings = json.load(f)

# Add DEBUG_MODE based on settings
DEBUG_MODE = settings.get("DEBUG", "False") == "True"


def get_foreign_institution_trend(stock_code):
    original_mode = settings.get("is_paper_trading", True)

    if original_mode:
        cfg["is_paper_trading"] = False
    else:
        logger.info("현재는 실전투자 상태입니다.")

    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    response = api.summarize_foreign_institution_estimates(stock_code)
    response_json = response.json()
    output2 = response_json.get("output2", [])

    if output2:
        # 시간대 기준으로 내림차순 정렬
        latest = max(output2, key=lambda x: int(x["bsop_hour_gb"]))
        frgn = int(latest["frgn_fake_ntby_qty"])
        orgn = int(latest["orgn_fake_ntby_qty"])

        return {"외국인": frgn, "기관": orgn}
    else:
        return {"외국인": 0, "기관": 0}

def get_foreign_net_trend(stock_code):
    original_mode = settings.get("is_paper_trading", True)

    if original_mode:
        cfg["is_paper_trading"] = False
    else:
        logger.info("현재는 실전투자 상태입니다.")

    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    response = api.summarize_foreign_net_estimates(stock_code)
    response_json = response.json()
    output = response_json.get("output", [])

    if output:
        # 시간대 기준으로 내림차순 정렬
        latest = max(output, key=lambda x: int(x["bsop_hour"]))
        glob_ntby_qty = int(latest["glob_ntby_qty"])
        return {"외국계": glob_ntby_qty}
    else:
        return {"외국계": 0}

def get_foreign_net_trade_by_stock():
    # 외국계 순매수/순매도 종합 데이터를 조회하는 함수
    original_mode = settings.get("is_paper_trading", True)

    if original_mode is True:
        cfg["is_paper_trading"] = False

    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    # 두 시장에 대해 순차적으로 호출
    results = []
    for market in ["1001", "2001"]:
        data = api.get_foreign_net_trading_summary(
            market=market,
        )
        logger.debug(f"📥 시장 {market}에서 {len(data)}개 종목 수신됨.")
        if isinstance(data, pd.DataFrame) and not data.empty:
            results.append(data)
        else:
            logger.warning(f"⚠️ 시장 {market}의 외국계 순매매 데이터가 없습니다.")
        time.sleep(1)  # 1초 대기

    merged = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    logger.debug(f"📦 최종 병합된 종목 수: {len(merged)}")

    # Explicitly cast column types if not empty
    if not merged.empty:
        merged = merged.astype({
            "stck_shrn_iscd": str,
            "hts_kor_isnm": str,
            "glob_ntsl_qty": int,
            "stck_prpr": int,
            "prdy_vrss": int,
            "prdy_vrss_sign": str,
            "prdy_ctrt": float,
            "acml_vol": int,
            "glob_total_seln_qty": int,
            "glob_total_shnu_qty": int,
        })

    # 컬럼 이름 변경
    rename_map = {
        "stck_shrn_iscd": "단축코드",
        "hts_kor_isnm": "종목명",
        "glob_ntsl_qty": "외국계순매도",
        "stck_prpr": "현재가",
        "prdy_vrss": "전일대비",
        "prdy_vrss_sign": "전일부호",
        "prdy_ctrt": "전일대비율",
        "acml_vol": "누적거래량",
        "glob_total_seln_qty": "외국계총매도",
        "glob_total_shnu_qty": "외국계총매수"
    }
    merged.rename(columns=rename_map, inplace=True)

    # Save merged DataFrame to CSV
    merged.to_csv(f"{CACHE_DIR}/foreign_net_summary.csv", index=False)

    # 전일부호 값 변환
    prdy_sign_map = {
        "1": "상한가",
        "2": "상승",
        "3": "보합",
        "4": "하한가",
        "5": "하락"
    }
    merged["전일부호"] = merged["전일부호"].map(prdy_sign_map).fillna(merged["전일부호"])

    # 표 형식으로 출력
    if not merged.empty:
        logger.info("📊 외국계 순매매 종합 데이터:")
        logger.info(merged.to_string(index=False))
    else:
        logger.warning("📭 최종 외국계 순매매 데이터가 비어 있습니다.")

    if original_mode is True:
        cfg["is_paper_trading"] = True
        logger.info("🔁 'is_paper_trading' 설정이 True로 복원되었습니다.")

    return merged

def get_program_trade_summary_by_time(stock_code, market):
    # 프로그램 매매현황에 대해 종목별로 조회하는 함수
    original_mode = settings.get("is_paper_trading", True)

    if original_mode is True:
        cfg["is_paper_trading"] = False

    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    data = api.get_program_trade_summary_by_time(
        stock_code=stock_code,
        market=market
    )

    logger.info(data)

    return data

# def get_total_trading_data(stock_code):
#
#     env = KoreaInvestEnv(cfg)
#     api = KoreaInvestAPI(cfg, env.get_base_headers())
#
#     response = api.get_current_price(stock_code)
#
#     output = response["output"][0] if isinstance(response.get("output"), list) else response
#     result = {
#         "현재가": output.get("stck_prpr"),
#         "52주 최고가": output.get("w52_hgpr"),
#         "52주 최고일자": output.get("w52_hgpr_date"),
#         "52주 최저가": output.get("w52_lwpr"),
#         "52주 최저일자": output.get("w52_lwpr_date"),
#         "52주 최고가 대비 현재가 비율": output.get("w52_hgpr_vrss_prpr_ctrt"),
#         "52주 최저가 대비 현재가 비율": output.get("w52_lwpr_vrss_prpr_ctrt"),
#         "누적거래량": output.get("acml_vol"),
#         "250일 최고가": output.get("d250_hgpr"),
#         "250일 최고일자": output.get("d250_hgpr_date"),
#         "250일 최저가": output.get("d250_lwpr"),
#         "250일 최저일자": output.get("d250_lwpr_date"),
#         "250일 최고가 대비 현재가 비율": output.get("d250_hgpr_vrss_prpr_rate"),
#         "250일 최저가 대비 현재가 비율": output.get("d250_lwpr_vrss_prpr_rate"),
#     }
#
#     type_map = {
#         "현재가": int,
#         "52주 최고가": int,
#         "52주 최고일자": str,
#         "52주 최저가": int,
#         "52주 최저일자": str,
#         "52주 최고가 대비 현재가 비율": float,
#         "52주 최저가 대비 현재가 비율": float,
#         "누적거래량": int,
#         "250일 최고가": int,
#         "250일 최고일자": str,
#         "250일 최저가": int,
#         "250일 최저일자": str,
#         "250일 최고가 대비 현재가 비율": float,
#         "250일 최저가 대비 현재가 비율": float,
#     }
#
#     for key, caster in type_map.items():
#         if key in result and result[key] is not None:
#             try:
#                 result[key] = caster(result[key])
#             except ValueError:
#                 pass  # Optionally log or handle conversion error
#
#     return result

def get_total_trading_data(stock_code):
    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    response = api.get_current_price(stock_code)
    output = response["output"][0] if isinstance(response.get("output"), list) else response

    # 누적거래량 추출 및 매핑
    acml_vol = output.get("acml_vol")
    print(acml_vol)

    try:
        return {"누적거래량": int(acml_vol)} if acml_vol is not None else {"누적거래량": 0}
    except ValueError:
        return {"누적거래량": 0}


if __name__ == "__main__":
    # get_foreign_institution_trend("005930")
    # get_foreign_net_trend("114090")
    get_total_trading_data("114090")
    # get_program_trade_summary_by_time("005930", "J")