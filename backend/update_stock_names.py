import FinanceDataReader as fdr
from slack_notifier import post_to_slack  # ✅ 슬랙 전송 모듈

CONFIG_PATH = "/Users/hyungseoklee/Documents/Leonardo/backend/config.yaml"

def main():
    try:
        print("📥 최신 종목 목록을 가져오는 중...")
        df = fdr.StockListing('KRX')[['Name', 'Code']]

        # ⬇️ 가나다 순으로 정렬
        df = df.sort_values(by='Name')

        # 저장 경로
        leo_project_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
        df.to_csv(leo_project_path, index=False, encoding="utf-8-sig")

        print(f"✅ stock_list.csv 저장 완료! (경로: {leo_project_path})")

        # ✅ 슬랙 알림
        post_to_slack("✅ 종목 리스트(stock_list.csv) 업데이트 완료", config_path=CONFIG_PATH)

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        post_to_slack(f"❌ 종목 리스트 업데이트 실패: {e}", config_path=CONFIG_PATH)

if __name__ == "__main__":
    main()