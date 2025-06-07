import requests
from bs4 import BeautifulSoup
import time

BASE_URL = "https://mfinance.finup.co.kr"
THEME_MAIN_URL = BASE_URL + "/Lab/ThemeLog"

def get_theme_links():
    res = requests.get(THEME_MAIN_URL)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    theme_links = {}
    for theme_box in soup.select("div.themeBox"):
        a_tag = theme_box.find("a")
        if not a_tag:
            continue
        theme_name = a_tag.text.strip().split("\n")[0]
        href = a_tag['href']
        theme_links[theme_name] = BASE_URL + href
    return theme_links

def get_theme_stocks(theme_url):
    res = requests.get(theme_url)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    stocks = []
    for row in soup.select("div.table-stocks tbody tr"):
        tds = row.select("td")
        if len(tds) > 1:
            stock_name = tds[0].text.strip()
            stocks.append(stock_name)
    return stocks

def crawl_finup_theme_stocks():
    themes = {}
    theme_links = get_theme_links()

    for theme, link in theme_links.items():
        print(f"📦 {theme} 크롤링 중...")
        try:
            stocks = get_theme_stocks(link)
            themes[theme] = stocks
            print(f"  ┗ 종목 수: {len(stocks)}")
        except Exception as e:
            print(f"  ❌ 오류: {e}")
        time.sleep(1)  # 서버 부하 방지
    return themes

# 실행 및 프린트
if __name__ == "__main__":
    theme_data = crawl_finup_theme_stocks()
    for theme, stocks in theme_data.items():
        print(f"\n🧩 {theme}:")
        print(", ".join(stocks))