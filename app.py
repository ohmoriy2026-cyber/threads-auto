import streamlit as st
import requests
from google import genai
import time
from PIL import Image
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import json

# ==========================================
# 🎨 デザイン・カスタムCSS
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide")

st.markdown("""
<style>
    .stApp, .main { background-color: #1A1A1D !important; }
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #26262B !important; border: 1px solid #3A3A40 !important; border-radius: 12px; padding: 20px; margin-bottom: 10px;
    }
    div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"], div[data-baseweb="base-input"],
    input, textarea, select, .stSelectbox div {
        background-color: #000000 !important; color: #FFFFFF !important; border: 1px solid #4A4A55 !important; border-radius: 8px !important;
    }
    div[role="listbox"], div[data-baseweb="popover"], div[data-baseweb="calendar"] {
        background-color: #000000 !important; color: #FFFFFF !important;
    }
    ::placeholder { color: #888888 !important; }
    label, p, h1, h2, h3, .stMarkdown { color: #F0F0F0 !important; font-weight: bold; }
    .stButton>button { background-color: #00E5FF !important; color: #000000 !important; font-weight: bold; border-radius: 8px; width: 100%; border: none; }
    
    /* データフレーム（表）のデザイン調整 */
    [data-testid="stDataFrame"] { background-color: #000000 !important; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群（ダッシュボード用データ取得を含む）
# ==========================================
def save_to_sheets(sheet_id, g_json, row_data):
    if not sheet_id or not g_json: return False
    try:
        creds_dict = json.loads(g_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"スプレッドシートエラー: {e}")
        return False

def get_sheet_data(sheet_id, g_json):
    """ダッシュボード用にスプレッドシートの全データを取得"""
    if not sheet_id or not g_json: return []
    try:
        creds_dict = json.loads(g_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        data = client.open_by_key(sheet_id).sheet1.get_all_values()
        if len(data) < 2: return []
        headers = data[0]
        # 空の行を除外して辞書型のリストに変換
        return [dict(zip(headers, row)) for row in data[1:] if any(row)]
    except:
        return []

def get_threads_engagement(token):
    """ダッシュボード用にThreadsのエンゲージメントを取得"""
    if not token: return []
    url = f"https://graph.threads.net/v1.0/me/threads?fields=id,text,like_count,reply_count,timestamp&access_token={token}"
    try:
        res = requests.get(url).json()
        return res.get("data", [])
    except:
        return []

def get_rakuten_ranking(app_id, access_key, genre_id):
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": app_id, "accessKey": access_key, "genreId": genre_id}
    try:
        res = requests.get(url, params=params, headers={"Referer": "https://localhost/"})
        return [item["Item"] for item in res.json().get("Items", [])[:10]]
    except: return []

def generate_post_text(item_name, price, target_str, tone, length, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"楽天商品「{item_name}」({price}円)を、ターゲット【{target_str}】に向けて、{tone}な感じで、約{length}文字で作って。挨拶なし、本文のみ。最後に「詳細はこちら👇」必須。"
    contents = [prompt, image] if image else prompt
    return client.models.generate_content(model='gemini-2.5-flash', contents=contents).text

def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    url = "https://graph.threads.net/v1.0/me/threads"
    params = {"access_token": access_token, "text": text, "media_type": "IMAGE" if image_url else "TEXT"}
    if image_url: params["image_url"] = image_url
    if reply_to_id: params["reply_to_id"] = reply_to_id
    try:
        res = requests.post(url, params=params)
        if res.status_code == 200:
            c_id = res.json().get("id")
            if image_url: time.sleep(10)
            requests.post("https://graph.threads.net/v1.0/me/threads_publish", params={"access_token": access_token, "creation_id": c_id})
            return c_id
    except: pass
    return None

# ==========================================
# 🖥️ メイン画面構成
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"", "rakuten_key":"", "gemini":"", "threads":"", "sheet_id":"", "g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "4. API設定"])

# ------------------------------------------
# 📊 1. ダッシュボードページ
# ------------------------------------------
if page == "1. ダッシュボード":
