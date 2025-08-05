import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import requests
from datetime import datetime
import time
import json # ここにjsonライブラリを追加

# Google Sheets設定
INPUT_SPREADSHEET_ID = '1ELh95L385GfNcJahAx1mUH4SZBHtKImBp_wAAsQALkM'
OUTPUT_SPREADSHEET_ID = '1Fn3AtGDRmEzn3Leu7-wVPU3KrO7rS1nMfdSG7bcYrLI'
DATE_STR = datetime.now().strftime('%y%m%d')

def get_google_sheet_client():
    """Google Sheetsクライアントを認証して返す"""
    credentials_json_str = os.getenv('GOOGLE_SERVICE_ACCOUNT_CREDENTIALS')
    if not credentials_json_str:
        raise ValueError("環境変数 'GOOGLE_SERVICE_ACCOUNT_CREDENTIALS' が設定されていません")

    # 環境変数から取得したJSON文字列を辞書に変換
    try:
        credentials = json.loads(credentials_json_str)
    except json.JSONDecodeError:
        raise ValueError("環境変数 'GOOGLE_SERVICE_ACCOUNT_CREDENTIALS' の形式が不正です。有効なJSON文字列を設定してください。")

    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
    client = gspread.authorize(creds)
    return client

def get_yahoo_news_urls(client):
    """入力スプレッドシートからYahoo!ニュースのURLを取得する"""
    try:
        spreadsheet = client.open_by_key(INPUT_SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet('URLリスト')
        urls = worksheet.col_values(1)[1:]  # ヘッダー行をスキップ
        return [url.strip() for url in urls if url.strip()]
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"スプレッドシートID: {INPUT_SPREADSHEET_ID} が見つかりません。")
        return []

def scrape_news(url):
    """指定されたURLのYahoo!ニュース記事からタイトルと本文をスクレイピングする"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 記事タイトルを取得
        title_element = soup.find('h1', class_='sc-dcJpzm iCqIeT')
        title = title_element.text.strip() if title_element else 'タイトル取得失敗'
        
        # 記事本文を取得
        article_text_element = soup.find('div', class_='sc-dcJpzm gLgWvM')
        article_text = article_text_element.text.strip() if article_text_element else '本文取得失敗'
        
        return title, article_text
    except requests.exceptions.RequestException as e:
        print(f"URL: {url} の取得中にエラーが発生しました: {e}")
        return '取得失敗', '取得失敗'

def write_to_google_sheet(client, data):
    """スクレイピングしたデータをスプレッドシートに書き込む"""
    try:
        spreadsheet = client.open_by_key(OUTPUT_SPREADSHEET_ID)
        # 現在の日付でワークシートを作成または取得
        try:
            worksheet = spreadsheet.worksheet(DATE_STR)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=DATE_STR, rows="100", cols="4")
        
        # ヘッダー行を設定
        if not worksheet.row_values(1):
            worksheet.append_row(['記事タイトル', '記事本文', 'URL', '取得日時'])
        
        # データを追記
        worksheet.append_rows(data)
        print(f"データをスプレッドシート '{DATE_STR}' に書き込みました。")
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"出力スプレッドシートID: {OUTPUT_SPREADSHEET_ID} が見つかりません。")

def main():
    """メイン処理"""
    print('スクリプトを開始します...')
    try:
        client = get_google_sheet_client()
        urls = get_yahoo_news_urls(client)
        
        if not urls:
            print("スクレイピング対象のURLがありません。")
            return
            
        scraped_data = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for url in urls:
            title, text = scrape_news(url)
            scraped_data.append([title, text, url, current_time])
            time.sleep(2)  # 連続アクセスを避けるための遅延
        
        if scraped_data:
            write_to_google_sheet(client, scraped_data)
        else:
            print("スクレイピングされたデータがありません。")

    except ValueError as e:
        print(e)
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")

if __name__ == '__main__':
    main()
