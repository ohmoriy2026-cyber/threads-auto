import gspread
from google.oauth2.service_account import Credentials
import json
import requests
import time
from datetime import datetime
import os

# GitHub Secretsから環境変数を読み込み
GEMINI_KEY = os.environ.get("GEMINI_KEY")
THREADS_TOKEN = os.environ.get("THREADS_TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
G_JSON = os.environ.get("G_JSON")

def post_to_threads(access_token, text, image_url=None):
    create_url = "https://graph.threads.net/v1.0/me/threads"
    params = {"access_token": access_token, "text": text}
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    
    res = requests.post(create_url, params=params)
    if res.status_code == 200:
        creation_id = res.json().get("id")
        if image_url: time.sleep(10) # 準備時間を長めに確保
        
        pub_res = requests.post("https://graph.threads.net/v1.0/me/threads_publish", 
                                params={"access_token": access_token, "creation_id": creation_id})
        return pub_res.json().get("id")
    return None

def main():
    if not all([THREADS_TOKEN, SHEET_ID, G_JSON]):
        print("設定が足りません")
        return

    # スプレッドシートに接続
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(G_JSON), scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    
    records = sheet.get_all_records()
    now = datetime.now()

    for i, row in enumerate(records):
        # statusがpending かつ 予約時間が現在時刻を過ぎている場合
        if row['status'] == 'pending':
            scheduled_time = datetime.strptime(row['scheduled_time'], '%Y-%m-%d %H:%M:%S')
            
            if scheduled_time <= now:
                print(f"投稿実行中: {row['item_name']}")
                
                # ① メイン投稿
                res_id = post_to_threads(THREADS_TOKEN, row['post_text'], row['image_url'])
                
                if res_id:
                    time.sleep(5)
                    # ② リプライ（リンク）
                    link_text = f"▼ 詳細はこちら\n{row['item_url']}"
                    post_to_threads(THREADS_TOKEN, link_text, image_url=None)
                    
                    # ステータスを更新（スプレッドシートは1行目がヘッダー、recordsは0開始なので i+2）
                    sheet.update_cell(i + 2, 6, "posted")
                    print("投稿成功！")
                else:
                    print("投稿失敗")

if __name__ == "__main__":
    main()
