import gspread
from google.oauth2.service_account import Credentials
import json
import requests
import time
from datetime import datetime
import os

# GitHub Secretsから環境変数を読み込み
THREADS_TOKEN = os.environ.get("THREADS_TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
G_JSON = os.environ.get("G_JSON")

def post_to_threads(access_token, text, image_url=None):
    create_url = "https://graph.threads.net/v1.0/me/threads"
    params = {"access_token": access_token, "text": text}
    # Threads APIには直接アクセス可能なURLが必要なため、J列(画像URL)を想定
    if image_url and image_url.startswith("http"):
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"
    
    try:
        res = requests.post(create_url, params=params)
        if res.status_code == 200:
            creation_id = res.json().get("id")
            if params["media_type"] == "IMAGE": time.sleep(10)
            
            pub_res = requests.post("https://graph.threads.net/v1.0/me/threads_publish", 
                                    params={"access_token": access_token, "creation_id": creation_id})
            return pub_res.json().get("id")
    except Exception as e:
        print(f"APIエラー: {e}")
    return None

def main():
    if not all([THREADS_TOKEN, SHEET_ID, G_JSON]):
        print("設定(Secrets)が不足しています。")
        return

    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(G_JSON), scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    
    # 全データを取得
    all_values = sheet.get_all_values()
    if not all_values: return
    
    headers = all_values[0] # 1行目
    rows = all_values[1:]   # 2行目以降
    now = datetime.now()

    for i, row_values in enumerate(rows):
        # 辞書形式に変換 (headersとrow_valuesの長さが違う場合を考慮)
        row = dict(zip(headers, row_values))
        
        # 投稿チェック(F列)が「予約中」や空欄の場合に処理 (画像に合わせて調整)
        status = row.get('投稿チェック', '')
        if status in ['', 'pending', '予約中']:
            try:
                # 投稿日(C), 時(D), 分(E) を組み合わせて日時に変換
                # 例: 2026/02/1 9:30
                date_str = f"{row['投稿日']} {row['時']}:{row['分']}:00"
                scheduled_time = datetime.strptime(date_str, '%Y/%m/%d %H:%M:%S')
                
                if scheduled_time <= now:
                    print(f"実行中: {row.get('本文', '')[:20]}...")
                    
                    # メイン投稿 (本文はB列)
                    # 画像URLはJ列(画像URL)を使用 (H列のGoogleドライブURLはAPIでは使えないため)
                    res_id = post_to_threads(THREADS_TOKEN, row.get('本文', ''), row.get('画像URL', ''))
                    
                    if res_id:
                        time.sleep(5)
                        # 返信(I列: 返信コメント内容)があれば投稿
                        reply_text = row.get('返信コメント内容', '')
                        if reply_text:
                            post_to_threads(THREADS_TOKEN, reply_text, image_url=None)
                        
                        # 投稿チェック(F列)を「完了」に更新
                        # スプレッドシートの列番号：F列は 6番目
                        sheet.update_cell(i + 2, 6, "完了")
                        print("✅ 投稿成功！")
                    else:
                        print("❌ 投稿失敗")
            except Exception as e:
                print(f"行 {i+2} の処理でエラー: {e}")

if __name__ == "__main__":
    main()
