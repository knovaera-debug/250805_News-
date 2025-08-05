import os
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import requests
import json

# 🔐 Google Sheets認証
try:
    with open('credentials.json', 'r') as f:
        credentials_info = json.load(f)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
    gc = gspread.authorize(credentials)
except Exception as e:
    print(f"❌ Error loading credentials: {e}")
    exit()

# ✅ スプレッドシートID設定
INPUT_SPREADSHEET_ID = '1ELh95L385GfNcJahAx1mUH4SZBHtKImBp_wAAsQALkM'
OUTPUT_SPREADSHEET_ID = '1Fn3AtGDRmEzn3Leu7-wVPU3KrO7rS1nMfdSG7bcYrLI'
DATE_STR = datetime.now().strftime('%y%m%d')

# ✅ Seleniumの設定（Headless Chrome）
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
browser = webdriver.Chrome(options=chrome_options)

# 📥 入力シートからURL取得
print(f"--- Getting URLs from sheet '{DATE_STR}' ---")
sh_input = gc.open_by_key(INPUT_SPREADSHEET_ID)
try:
    input_ws = sh_input.worksheet(DATE_STR)
    input_urls = [url for url in input_ws.col_values(3)[1:] if url]
    print(f"✅ Found {len(input_urls)} URLs to process.")
except gspread.WorksheetNotFound:
    print(f"❌ Worksheet '{DATE_STR}' not found in input spreadsheet. Exiting.")
    browser.quit()
    exit()

# 📤 出力シートの準備
sh_output = gc.open_by_key(OUTPUT_SPREADSHEET_ID)
print(f"--- Preparing output sheet for '{DATE_STR}' ---")

# 既存シートがあれば削除
if DATE_STR in [ws.title for ws in sh_output.worksheets()]:
    sh_output.del_worksheet(sh_output.worksheet(DATE_STR))
    print(f"🗑️ Existing sheet '{DATE_STR}' deleted.")

# 新しい出力シート作成
new_ws = sh_output.add_worksheet(title=DATE_STR, rows="1000", cols="50")
header = ['No.', 'タイトル', 'URL', '発行日時', '本文']
comment_cols = ['コメント数', 'コメント']
full_header = [''] * 15
full_header[0:5] = header
full_header[14] = 'コメント数'
full_header[15:] = ['コメント'] * (50 - 15)
new_ws.update('A1:AX1', [full_header])
print(f"✅ Created new sheet: {DATE_STR}")

# 📰 ニュース記事とコメントの処理
print("--- Starting scraping job ---")
all_data_to_write = []

for idx, base_url in enumerate(input_urls, start=1):
    try:
        print(f"\n▶️ Processing {idx}/{len(input_urls)}: {base_url}")
        headers_req = {'User-Agent': 'Mozilla/5.0'}

        # ✅ 記事本文取得（複数ページ対応）
        article_bodies = []
        page = 1
        title = '取得不可'
        article_date = '取得不可'

        while True:
            url = base_url if page == 1 else f"{base_url}?page={page}"
            res = requests.get(url, headers=headers_req)
            soup = BeautifulSoup(res.text, 'html.parser')

            if page == 1:
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True).replace(' - Yahoo!ニュース', '') if title_tag else '取得不可'
                date_tag = soup.find('time')
                article_date = date_tag.get_text(strip=True) if date_tag else '取得不可'

            article = soup.find('article')
            if article:
                paragraphs = article.find_all('p')
                body_text = '\n'.join([p.get_text(strip=True) for p in paragraphs])
            else:
                body_text = ''

            if not body_text or body_text in article_bodies:
                break

            article_bodies.append(body_text)
            page += 1
            if page > 10:
                break

        print(f"📰 Title: {title}")
        print(f"🕒 Date: {article_date}")
        print(f"📄 Pages: {len(article_bodies)}")

        # ✅ コメント取得（Selenium + 複数ページ）
        comments = []
        comment_page = 1

        while True:
            comment_url = f"{base_url}/comments?page={comment_page}"
            browser.get(comment_url)
            time.sleep(2)

            soup_comments = BeautifulSoup(browser.page_source, 'html.parser')
            comment_elements = soup_comments.find_all('p', class_='sc-169yn8p-10')
            page_comments = [p.get_text(strip=True) for p in comment_elements]

            if not page_comments or page_comments[0] in comments:
                break

            comments.extend(page_comments)
            comment_page += 1
            if comment_page > 10:
                break

        print(f"💬 Comments: {len(comments)}")

        # ✅ 書き込みデータ構築
        row_data = [idx, title, base_url, article_date, article_bodies[0]]
        row_data.extend([''] * 9)
        row_data.append(len(comments))
        row_data.extend(comments[:35])  # 最大35コメント（A〜AX列に収める）
        all_data_to_write.append(row_data)

        for i in range(1, len(article_bodies)):
            all_data_to_write.append([''] * 4 + [article_bodies[i]] + [''] * 45)

    except Exception as e:
        print(f"❌ Error at URL {idx}: {e}")
        continue

# ✅ シートに一括書き込み
if all_data_to_write:
    new_ws.update(f"A2", all_data_to_write)
    print("\n✅ All data written to output sheet.")
else:
    print("\n⚠️ No data to write.")

browser.quit()
print("--- ✅ Scraping completed ---")
