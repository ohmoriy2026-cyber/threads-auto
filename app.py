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
# 🎨 デザイン・カスタムCSS（全ての白枠を完全に消し去る）
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide")

st.markdown("""
<style>
    /* 全体の背景 */
    .stApp, .main { background-color: #1A1A1D !important; }
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }
    
    /* ブロックごとの枠 */
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #26262B !important; 
        border: 1px solid #3A3A40 !important; 
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 10px;
    }

    /* 🌟 全ての入力欄（テキスト、日付、時間、ドロップダウン）を黒背景・白文字に */
    div[data-baseweb="input"], 
    div[data-baseweb="textarea"], 
    div[data-baseweb="select"],
    div[data-baseweb="base-input"],
    input, textarea, .stSelectbox div {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        border: 1px solid #4A4A55 !important;
    }

    /* 日付・時間選択時のポップアップ内も黒にする */
    div[role="listbox"], div[data-baseweb="popover"] {
        background-color: #000000 !important;
    }

    /* ラベル文字 */
    label, p, h1, h2, h3, .stMarkdown { color: #F0F0F0 !important; font-weight: bold; }

    /* ボタンのデザイン */
    .stButton>button { 
        background-color: #00E5FF !important; 
        color: #000000 !important; 
        font-weight: bold; 
        border-radius: 8px; 
        width: 100%;
        border: none;
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

def save_to_sheets(sheet_id, g_json, row):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(g_json), scopes=scopes)
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row)
        return True
    except: return False

# ==========================================
# 🖥️ UI
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"", "rakuten_key":"", "gemini":"", "threads":"", "sheet_id":"", "g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "4. API設定"])

if page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード"):
        pw = st.text_input("合言葉", type="password", key="master_pw_input")
        if st.button("ロード", key="load_btn"):
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
        r_id = c1.text_input("楽天ID", value=api["rakuten_id"], type="password", key="ri_f")
        r_key = c1.text_input("楽天Key", value=api["rakuten_key"], type="password", key="rk_f")
        g_key = c1.text_input("Gemini", value=api["gemini"], type="password", key="gk_f")
        t_tok = c2.text_input("Threads", value=api["threads"], type="password", key="tt_f")
        s_id = c2.text_input("Sheet ID", value=api["sheet_id"], key="si_f")
        g_js = c2.text_area("JSON", value=api["g_json"], height=100, key="gj_f")
        if st.button("設定を保存", key="save_final_btn"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("保存しました！")

elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約投稿")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]: st.warning("API設定を先に済ませてください。")
    else:
        with st.container(border=True):
            genres_dict = {"総合": "0", "レディース": "100371", "メンズ": "551177", "美容": "100939", "食品": "100227", "家電": "562631", "ベビー": "100533"}
            sel_name = st.selectbox("ジャンル", list(genres_dict.keys()), key="full_gen_box")
            if st.button("ランキング取得", key="get_rank_btn"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], genres_dict[sel_name])

        if "items" in st.session_state:
            selected = []
            for i, item in enumerate(st.session_state["items"]):
                with st.container(border=True):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    c2.write(f"**{item['itemName'][:50]}...**")
                    # 🌟 修正：キーを "chk_item_..." に変更（重複回避）
                    if c2.checkbox("選ぶ", key=f"chk_item_{i}"):
                        u_img = c2.file_uploader("画像", type=["jpg","png"], key=f"file_up_{i}")
                        item["user_img"] = u_img
                        selected.append(item)
            
            if selected:
                st.divider()
                with st.container(border=True):
                    st.subheader("ターゲット・文字数設定")
                    c1, c2, c3 = st.columns(3)
                    with c1: gender = st.radio("性別", ["女性", "男性", "指定なし"], key="g_sel")
                    with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="a_sel")
                    with c3: kids = st.radio("子供", ["なし", "未就学児", "小学生"], key="k_sel")
                    tone = st.selectbox("トーン", ["エモい", "役立つ", "元気"], key="t_sel")
                    length = st.slider("文字数", 50, 500, 150, step=10, key="l_sel")
                    
                    if st.button(f"✨ {len(selected)}件の文章を生成", key="gen_all_btn"):
                        t_str = f"{gender}, 年代:{','.join(age)}, 子供:{kids}"
                        res = []
                        pb = st.progress(0)
                        for j, s_item in enumerate(selected):
                            img_obj = Image.open(s_item["user_img"]) if s_item["user_img"] else None
                            txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], t_str, tone, length, api["gemini"], img_obj)
                            res.append({"item": s_item, "text": txt})
                            pb.progress((j+1)/len(selected))
                        st.session_state["final_res"] = res

        if "final_res" in st.session_state:
            for k, p in enumerate(st.session_state["final_res"]):
                item = p["item"]
                with st.expander(f"確認: {item['itemName'][:30]}", expanded=True):
                    # 🌟 修正：全てのキーに固有の名前を付けました
                    f_txt = st.text_area("本文", value=p["text"], key=f"final_txt_area_{k}", height=150)
                    use_img = st.checkbox("画像あり", value=True, key=f"use_img_chk_{k}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 即時投稿", key=f"post_now_btn_{k}"):
                        i_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                        mid = post_to_threads(api["threads"], f_txt, image_url=i_url)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], f"▼ 詳細はこちら\n{item['itemUrl']}", reply_to_id=mid)
                            st.success("成功！")
                    
                    with c_sch:
                        d = st.date_input("予約日", key=f"res_date_in_{k}")
                        t = st.time_input("時間", key=f"res_time_in_{k}")
                        # 🌟 修正：ここがエラーの場所でした！キーを "reserve_sheet_btn_..." に変更
                        if st.button("🗓️ 予約リストに追加", key=f"reserve_sheet_btn_{k}"):
                            row = ["", f_txt, d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", f"▼ 詳細はこちら\n{item['itemUrl']}", item["mediumImageUrls"][0]["imageUrl"] if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                st.success("予約完了！")

elif page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
