import pandas as pd
import os

# 현재 파일의 위치를 기준으로 절대경로 생성
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_LIST_PATH = os.path.join(BASE_DIR, 'cache', 'stock_list.csv')

# CSV 불러오기
stock_df = pd.read_csv(STOCK_LIST_PATH, dtype={'Code': str})

def get_stock_name_by_code(code):
    """
    종목코드(code)를 입력받아 해당 종목명을 반환.
    코드가 없으면 None 반환.
    """
    try:
        name = stock_df.loc[stock_df['Code'] == code, 'Name'].values
        return name[0] if len(name) > 0 else None
    except Exception as e:
        return None