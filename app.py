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
# 🎨 デザイン・カスタムCSS（視認性と操作性を極限まで追求）
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide")

st.markdown("""
<style>
    .stApp, .main { background-color: #1A1A1D !important; }
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }
    
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #26262B !important; 
        border: 1px solid #3A3A40 !important; 
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 10px;
    }

    /* 全ての入力欄（背景ブラック、文字ホワイト） */
    div[data-baseweb="input"], 
    div[data-baseweb="textarea"], 
    div[data-baseweb="select"],
    div[data-baseweb="base-input"],
    .stTextInput input, .stTextArea textarea, .stSelectbox div {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
    }

    /* セレクトボックスのドロップダウン */
    div[role="listbox"] ul li {
        background-color: #000000 !important;
        color: #FFFFFF !important;
    }

    /* 文字色全般 */
    label, p, h1, h2, h3, .stMarkdown { color: #F0F0F0 !important; font-weight: bold; }

    /* ボタン */
    .stButton>button { 
        background-color: #00E5FF !important; 
        color: #000000 !important; 
        font-weight: bold; 
        border-radius: 8px; 
        width: 100%;
        border: none;
        padding: 10px;
    }
    .stButton>button:hover { 
        background-color: #00B8CC !important; 
        box-shadow: 0 4px 15px rgba(0, 229, 255, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群
# ==========================================

def get_rakuten_ranking(app_id, access_key, genre_id):
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": app_id, "accessKey": access_key, "genreId": genre_id}
    try:
        res = requests.get(url, params=params, headers={"Referer": "https://localhost/"})
        return [item["Item"] for item in res.json().get("Items", [])[:10]]
    except: return []

def generate_post_text(item_name, price, target_str, tone, length, api_key, image=None):
    client = genai.Client(api_key=api_key)
    # 文字数の指示をプロンプトに追加
    prompt = f"""楽天商品「{item_name}」({price}円)を、ターゲット【{target_str}】に向けて紹介するThreads投稿文を作成してください。
【トーン】{tone}
【文字数】{length}文字程度
【条件】
・挨拶や前置きは一切書かず、本文のみを出力すること。
・最後に必ず「詳細はこちら👇」を入れること。
・絵文字を使い、Threadsで目に留まりやすい構成にすること。"""
    
    contents = [prompt, image] if image else prompt
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=contents)
        return response.text
    except Exception as e:
        return f"AIエラー: {e}"

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

def save_to_sheets(sheet_id, g_json, row):
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
# 🖥️ UI・ロジック
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"", "rakuten_key":"", "gemini":"", "threads":"", "sheet_id":"", "g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "4. API設定"])

# --- 4. API設定 ---
if page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード"):
        pw = st.text_input("合言葉", type="password")
        if st.button("ロード"):
            if pw == st.secrets.get("master_password", "admin123"):
                st.session_state["api_keys"] = {
                    "rakuten_id": st.secrets.get("rakuten_id", ""), "rakuten_key": st.secrets.get("rakuten_key", ""),
                    "gemini": st.secrets.get("gemini_key", ""), "threads": st.secrets.get("threads_token", ""),
                    "sheet_id": st.secrets.get("sheet_id", ""), "g_json": st.secrets.get("g_json", "")
                }
                st.success("成功！保存を押してください。")

    with st.container(border=True):
        api = st.session_state["api_keys"]
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天ID", value=api["rakuten_id"], type="password", key="rk1")
        r_key = c1.text_input("楽天Key", value=api["rakuten_key"], type="password", key="rk2")
        g_key = c1.text_input("Gemini API", value=api["gemini"], type="password", key="gk1")
        t_tok = c2.text_input("Threadsトークン", value=api["threads"], type="password", key="th1")
        s_id = c2.text_input("スプレッドシートID", value=api["sheet_id"], key="si1")
        g_js = c2.text_area("JSON鍵", value=api["g_json"], height=100, key="gj1")
        if st.button("設定を保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("保存完了")

# --- 2. 商品作成＆予約 ---
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約投稿")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]: st.warning("API設定を先に済ませてください。")
    else:
        with st.container(border=True):
            st.subheader("STEP 1: ジャンル選択")
            genres_dict = {
                "総合": "0", "レディースファッション": "100371", "メンズファッション": "551177", 
                "美容・コスメ": "100939", "食品": "100227", "スイーツ": "551167", "家電": "562631",
                "キッズ・ベビー": "100533", "おもちゃ": "101164", "日用品": "215783", "その他(ID指定)": "custom"
            }
            sel_name = st.selectbox("ジャンル", list(genres_dict.keys()), key="gen_box")
            target_id = genres_dict[sel_name]
            if target_id == "custom":
                target_id = st.text_input("ジャンルIDを入力", key="custom_id")
            
            if st.button("ランキング取得"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], target_id)

        if "items" in st.session_state:
            st.subheader("STEP 2: 商品選択")
            selected = []
            for i, item in enumerate(st.session_state["items"]):
                with st.container(border=True):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    c2.write(f"**{item['itemName'][:60]}...**")
                    if c2.checkbox("選ぶ", key=f"s_{i}"):
                        u_img = c2.file_uploader("参考画像", type=["jpg","png"], key=f"u_{i}")
                        item["user_img"] = u_img
                        selected.append(item)
            
            if selected:
                st.divider()
                st.subheader("STEP 3: ターゲット・文字数・トーン設定")
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1: gender = st.radio("性別", ["女性", "男性", "指定なし"], key="g1")
                    with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="a1")
                    with c3: kids = st.radio("家族構成", ["指定なし", "未就学児あり", "小学生あり"], key="k1")
                    
                    tone = st.selectbox("トーン", ["エモい", "役立つ系", "共感", "元気"], key="tone1")
                    # 🌟 文字数指定スライダーの追加
                    char_limit = st.slider("文字数の目安（Threads上限500文字）", 50, 500, 150, step=10, key="char_limit")
                    
                    if st.button(f"✨ {len(selected)}件の文章を生成"):
                        target_str = f"{gender}, 年代:{','.join(age)}, 子供:{kids}"
                        results = []
                        pb = st.progress(0)
                        for j, s_item in enumerate(selected):
                            img_obj = Image.open(s_item["user_img"]) if s_item["user_img"] else None
                            txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], target_str, tone, char_limit, api["gemini"], img_obj)
                            results.append({"item": s_item, "text": txt})
                            pb.progress((j+1)/len(selected))
                        st.session_state["final_res"] = results

        if "final_res" in st.session_state:
            st.subheader("STEP 4: 最終確認 ＆ 予約")
            for k, p in enumerate(st.session_state["final_res"]):
                item = p["item"]
                with st.expander(f"編集: {item['itemName'][:30]}", expanded=True):
                    f_txt = st.text_area("本文", value=p["text"], key=f"f_txt_{k}", height=150)
                    use_img = st.checkbox("商品画像を添付", value=True, key=f"ui_{k}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 即時投稿", key=f"n_btn_{k}"):
                        img_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                        mid = post_to_threads(api["threads"], f_txt, image_url=img_url)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], f"▼ 詳細はこちら\n{item['itemUrl']}", reply_to_id=mid)
                            st.success("成功！")
                    
                    with c_sch:
                        d = st.date_input("予約日", key=f"d_{k}")
                        t = st.time_input("時間", key=f"t_{k}")
                        if st.button("🗓️ 予約登録", key=f"s_btn_{k}"):
                            row = ["", f_txt, d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", f"▼ 詳細はこちら\n{item['itemUrl']}", item["mediumImageUrls"][0]["imageUrl"] if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                st.success("予約完了")

elif page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
