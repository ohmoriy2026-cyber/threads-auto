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
# 🎨 デザイン・カスタムCSS（すべての入力欄をダークに）
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide")

st.markdown("""
<style>
    /* ページ全体 */
    .stApp, .main { background-color: #1A1A1D !important; }
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }
    
    /* 枠組み */
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #26262B !important; 
        border: 1px solid #3A3A40 !important; 
        border-radius: 12px;
        padding: 20px;
    }

    /* 🌟 全ての入力欄（テキスト、エリア、日付、時間、セレクトボックス）をダークに */
    div[data-baseweb="input"], 
    div[data-baseweb="textarea"], 
    div[data-baseweb="select"],
    div[data-baseweb="base-input"] {
        background-color: #121214 !important;
        border: 1px solid #4A4A55 !important;
        border-radius: 8px !important;
    }
    
    /* 入力中の文字色を白で固定 */
    input, textarea, span, div {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    /* ラベルの色 */
    label, p, h1, h2, h3 { color: #F0F0F0 !important; }

    /* ボタン */
    .stButton>button { 
        background-color: #00E5FF !important; 
        color: #000000 !important; 
        font-weight: bold; 
        border-radius: 8px; 
        width: 100%;
        transition: 0.3s;
    }
    .stButton>button:hover { 
        background-color: #00B8CC !important; 
        transform: scale(1.01);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 共通関数
# ==========================================

def get_rakuten_ranking(app_id, access_key, genre_id):
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": app_id, "accessKey": access_key, "genreId": genre_id}
    headers = {"Referer": "https://localhost/"}
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return [item["Item"] for item in response.json().get("Items", [])[:10]]
    except: pass
    return []

def generate_post_text(item_name, price, target, tone, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"楽天商品「{item_name}」({price}円)を、{target}向けに{tone}で紹介するThreads投稿文を作成してください。挨拶なし、本文のみ。最後に「詳細はこちら👇」必須。"
    contents = [prompt, image] if image else prompt
    res = client.models.generate_content(model='gemini-2.5-flash', contents=contents)
    return res.text

def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    create_url = "https://graph.threads.net/v1.0/me/threads"
    params = {"access_token": access_token, "text": text}
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"
    if reply_to_id: params["reply_to_id"] = reply_to_id
    
    res = requests.post(create_url, params=params)
    if res.status_code == 200:
        c_id = res.json().get("id")
        if image_url: time.sleep(10)
        pub_res = requests.post("https://graph.threads.net/v1.0/me/threads_publish", params={"access_token": access_token, "creation_id": c_id})
        return pub_res.json().get("id") if pub_res.status_code == 200 else None
    return None

def save_to_sheets(sheet_id, g_json, row_data):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(g_json), scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        sheet.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"保存失敗: {e}")
        return False

# ==========================================
# 🖥️ メイン画面
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"", "rakuten_key":"", "gemini":"", "threads":"", "sheet_id":"", "g_json":""}

st.sidebar.title("📱 メニュー")
page = st.sidebar.radio("移動先", ["1. ダッシュボード", "2. 商品作成＆予約投稿", "4. API設定"])

if page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者ログイン"):
        pw = st.text_input("合言葉", type="password")
        if st.button("管理者キーをロード"):
            if pw == st.secrets.get("master_password", "admin123"):
                st.session_state["api_keys"] = {
                    "rakuten_id": st.secrets.get("rakuten_id", ""),
                    "rakuten_key": st.secrets.get("rakuten_key", ""),
                    "gemini": st.secrets.get("gemini_key", ""),
                    "threads": st.secrets.get("threads_token", ""),
                    "sheet_id": st.secrets.get("sheet_id", ""),
                    "g_json": st.secrets.get("g_json", "")
                }
                st.success("ロード完了！")

    with st.container(border=True):
        api = st.session_state["api_keys"]
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天 ID", value=api["rakuten_id"], type="password")
        r_key = c1.text_input("楽天 Key", value=api["rakuten_key"], type="password")
        g_key = c1.text_input("Gemini Key", value=api["gemini"], type="password")
        t_tok = c2.text_input("Threads Token", value=api["threads"], type="password")
        s_id = c2.text_input("Sheet ID", value=api["sheet_id"])
        g_js = c2.text_area("Service Account JSON", value=api["g_json"], height=100)
        
        if st.button("設定を保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("保存しました！")

elif page == "2. 商品作成＆予約投稿":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]:
        st.warning("先に設定画面でキーを保存してください。")
    else:
        genres = {"総合": "0", "レディース": "100371", "メンズ": "551177", "家電": "211742"}
        sel_genre = st.selectbox("ジャンル", list(genres.keys()))
        if st.button("ランキング取得"):
            st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], genres[sel_genre])
        
        if "items" in st.session_state:
            selected = []
            for i, item in enumerate(st.session_state["items"]):
                with st.container(border=True):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    c2.write(f"**{item['itemName'][:50]}...**")
                    if c2.checkbox("選択", key=f"sel_{i}"):
                        img = c2.file_uploader("参考画像", type=["jpg","png"], key=f"img_{i}")
                        item["user_img"] = img
                        selected.append(item)
            
            if selected:
                st.divider()
                target = st.text_input("ターゲット", "30代女性、共感重視", key="target_input")
                tone = st.selectbox("トーン", ["エモい", "役立つ", "共感"], key="tone_select")
                if st.button(f"✨ {len(selected)}件の文章を生成"):
                    posts = []
                    bar = st.progress(0)
                    for j, s_item in enumerate(selected):
                        u_img = Image.open(s_item["user_img"]) if s_item["user_img"] else None
                        txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], target, tone, api["gemini"], u_img)
                        posts.append({"item": s_item, "text": txt})
                        bar.progress((j+1)/len(selected))
                    st.session_state["gen_posts"] = posts

        if "gen_posts" in st.session_state:
            for k, p in enumerate(st.session_state["gen_posts"]):
                item = p["item"]
                with st.expander(f"編集: {item['itemName'][:30]}", expanded=True):
                    # 🌟 重複エラー修正：keyの名前をバラバラにしました
                    f_txt = st.text_area("本文", value=p["text"], key=f"final_text_{k}", height=150)
                    use_img = st.checkbox("画像添付", value=True, key=f"use_img_{k}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 即時投稿", key=f"now_btn_{k}"):
                        img_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                        mid = post_to_threads(api["threads"], f_txt, image_url=img_url)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], f"▼ 詳細はこちら\n{item['itemUrl']}", reply_to_id=mid)
                            st.success("投稿成功！")
                    
                    with c_sch:
                        d = st.date_input("予約日", key=f"date_input_{k}")
                        t = st.time_input("時間", key=f"time_input_{k}") # 🌟ここを time_input_{k} に修正
                        if st.button("🗓️ 予約登録", key=f"sch_btn_{k}"):
                            row = ["", f_txt, d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", f"▼ 詳細はこちら\n{item['itemUrl']}", item["mediumImageUrls"][0]["imageUrl"] if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                st.success("予約完了！")

elif page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
