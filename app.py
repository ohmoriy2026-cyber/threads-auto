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
# 🎨 デザイン・カスタムCSS（視認性を最優先）
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide")

st.markdown("""
<style>
    /* 全体の背景 */
    .stApp, .main { background-color: #1A1A1D !important; }
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }
    
    /* 枠組み */
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #26262B !important; 
        border: 1px solid #3A3A40 !important; 
        border-radius: 12px;
        padding: 20px;
    }

    /* 🌟 全ての入力欄（背景を濃く、文字を白く） */
    div[data-baseweb="input"], 
    div[data-baseweb="textarea"], 
    div[data-baseweb="select"],
    div[data-baseweb="base-input"],
    .stTextInput input, .stTextArea textarea {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        border: 1px solid #4A4A55 !important;
    }

    /* セレクトボックスの選択肢と文字色 */
    div[role="listbox"], div[data-baseweb="popover"] {
        background-color: #000000 !important;
        color: #FFFFFF !important;
    }

    /* ラベル文字 */
    label, p, h1, h2, h3, .stMarkdown { color: #F0F0F0 !important; font-weight: bold; }

    /* ボタン */
    .stButton>button { 
        background-color: #00E5FF !important; 
        color: #000000 !important; 
        font-weight: bold; 
        border-radius: 8px; 
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数
# ==========================================

def get_rakuten_ranking(app_id, access_key, genre_id):
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": app_id, "accessKey": access_key, "genreId": genre_id}
    try:
        res = requests.get(url, params=params, headers={"Referer": "https://localhost/"})
        return [item["Item"] for item in res.json().get("Items", [])[:10]]
    except: return []

def generate_post_text(item_name, price, target_str, tone, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"楽天商品「{item_name}」({price}円)を、ターゲット【{target_str}】に向けて、トーン【{tone}】でThreads投稿文を作って。挨拶抜き、本文のみ。最後に「詳細はこちら👇」必須。"
    contents = [prompt, image] if image else prompt
    return client.models.generate_content(model='gemini-2.5-flash', contents=contents).text

def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    create_url = "https://graph.threads.net/v1.0/me/threads"
    params = {"access_token": access_token, "text": text, "media_type": "IMAGE" if image_url else "TEXT"}
    if image_url: params["image_url"] = image_url
    if reply_to_id: params["reply_to_id"] = reply_to_id
    
    try:
        res = requests.post(create_url, params=params)
        if res.status_code == 200:
            c_id = res.json().get("id")
            if image_url: time.sleep(10)
            pub = requests.post("https://graph.threads.net/v1.0/me/threads_publish", params={"access_token": access_token, "creation_id": c_id})
            return pub.json().get("id")
    except: pass
    return None

def save_to_sheets(sheet_id, g_json, row):
    if not g_json or not sheet_id: return False
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(g_json), scopes=scopes)
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row)
        return True
    except Exception as e:
        st.error(f"保存失敗: {e}")
        return False

# ==========================================
# 🖥️ セッション初期化
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"", "rakuten_key":"", "gemini":"", "threads":"", "sheet_id":"", "g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "4. API設定"])

# --- API設定ページ ---
if page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード"):
        pw = st.text_input("合言葉", type="password")
        if st.button("管理者キーをロード"):
            if pw == st.secrets.get("master_password", "admin123"):
                st.session_state["api_keys"] = {
                    "rakuten_id": st.secrets.get("rakuten_id", ""), "rakuten_key": st.secrets.get("rakuten_key", ""),
                    "gemini": st.secrets.get("gemini_key", ""), "threads": st.secrets.get("threads_token", ""),
                    "sheet_id": st.secrets.get("sheet_id", ""), "g_json": st.secrets.get("g_json", "")
                }
                st.success("ロード完了！")

    with st.container(border=True):
        api = st.session_state["api_keys"]
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天 App ID", value=api["rakuten_id"], type="password", key="ri")
        r_key = c1.text_input("楽天 Access Key", value=api["rakuten_key"], type="password", key="rk")
        g_key = c1.text_input("Gemini API Key", value=api["gemini"], type="password", key="gk")
        t_tok = c2.text_input("Threads Token", value=api["threads"], type="password", key="tt")
        s_id = c2.text_input("Spreadsheet ID", value=api["sheet_id"], key="si")
        g_js = c2.text_area("Service Account JSON", value=api["g_json"], height=150, key="gj")
        if st.button("設定を保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("設定を保存しました。")

# --- メインページ ---
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約投稿")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]: st.warning("API設定を行ってください。")
    else:
        with st.container(border=True):
            genres = {"総合": "0", "レディース": "100371", "メンズ": "551177", "家電": "211742", "美容": "100939"}
            sel_genre = st.selectbox("ランキングジャンル", list(genres.keys()))
            if st.button("最新ランキングを取得"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], genres[sel_genre])
        
        if "items" in st.session_state:
            st.subheader("STEP 1: 商品選択")
            selected = []
            for i, item in enumerate(st.session_state["items"]):
                with st.container(border=True):
                    col1, col2 = st.columns([1, 4])
                    col1.image(item["mediumImageUrls"][0]["imageUrl"])
                    col2.write(f"**{item['itemName'][:60]}...**")
                    if col2.checkbox("この商品を選択", key=f"sel_{i}"):
                        img = col2.file_uploader("参考画像(任意)", type=["jpg","png"], key=f"img_{i}")
                        item["user_img"] = img
                        selected.append(item)
            
            if selected:
                st.divider()
                st.subheader("STEP 2: ターゲット・トーン設定")
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    gender = c1.radio("性別", ["女性", "男性", "指定なし"])
                    age = c2.multiselect("年代", ["10代", "20代", "30代", "40代", "50代以上"], default=["20代", "30代"])
                    kids = c3.radio("家族構成", ["指定なし", "未就学児あり", "小学生あり"])
                    tone = st.selectbox("文章のトーン", ["エモい", "役立つ", "共感", "ハイテンション"], key="tone_p2")
                    
                    if st.button(f"✨ {len(selected)}件の文章を生成"):
                        target_str = f"性別:{gender}, 年代:{','.join(age)}, 子供:{kids}"
                        posts = []
                        bar = st.progress(0)
                        for j, s_item in enumerate(selected):
                            u_img = Image.open(s_item["user_img"]) if s_item["user_img"] else None
                            txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], target_str, tone, api["gemini"], u_img)
                            posts.append({"item": s_item, "text": txt})
                            bar.progress((j+1)/len(selected))
                        st.session_state["gen_posts"] = posts

        if "gen_posts" in st.session_state:
            st.subheader("STEP 3: 最終確認 ＆ 予約登録")
            for k, p in enumerate(st.session_state["gen_posts"]):
                item = p["item"]
                with st.expander(f"編集: {item['itemName'][:30]}", expanded=True):
                    f_txt = st.text_area("本文", value=p["text"], key=f"f_txt_{k}", height=150)
                    use_img = st.checkbox("商品画像を添付する", value=True, key=f"u_img_{k}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 今すぐ投稿", key=f"n_btn_{k}"):
                        img_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                        mid = post_to_threads(api["threads"], f_txt, image_url=img_url)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], f"▼ 詳細はこちら\n{item['itemUrl']}", reply_to_id=mid)
                            st.success("投稿しました！")
                    
                    with c_sch:
                        sch_d = st.date_input("予約日", key=f"d_in_{k}")
                        sch_t = st.time_input("時間", key=f"t_in_{k}")
                        if st.button("🗓️ 予約登録", key=f"s_btn_{k}"):
                            # シートの列順: NO, 本文, 投稿日, 時, 分, 投稿チェック, 投稿URL, ドライブURL, 返信, 画像URL
                            row = ["", f_txt, sch_d.strftime('%Y/%m/%d'), str(sch_t.hour), str(sch_t.minute), "pending", "", "", f"▼ 詳細はこちら\n{item['itemUrl']}", item["mediumImageUrls"][0]["imageUrl"] if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                st.success(f"予約完了: {sch_d} {sch_t}")
