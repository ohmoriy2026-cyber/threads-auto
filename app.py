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
        background-color: #26262B !important; 
        border: 1px solid #3A3A40 !important; 
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 10px;
    }

    /* 入力欄（背景ブラック、文字ホワイト） */
    div[data-baseweb="input"], 
    div[data-baseweb="textarea"], 
    div[data-baseweb="select"],
    div[data-baseweb="base-input"],
    .stTextInput input, .stTextArea textarea, .stSelectbox div {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
    }

    /* セレクトボックスのドロップダウンリスト */
    div[role="listbox"] ul li {
        background-color: #000000 !important;
        color: #FFFFFF !important;
    }
    div[role="listbox"] ul li:hover {
        background-color: #333333 !important;
    }

    /* 文字色 */
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
        transform: scale(1.01);
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
        if res.status_code == 200:
            return [item["Item"] for item in res.json().get("Items", [])[:10]]
    except: pass
    return []

def generate_post_text(item_name, price, target_str, tone, length, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"""楽天商品「{item_name}」({price}円)を、ターゲット【{target_str}】に向けて紹介するThreads投稿文を作成してください。
【トーン】{tone}
【文字数】{length}文字程度
【条件】
・挨拶や前置きは一切不要、本文のみを出力。
・最後に必ず「詳細はこちら👇」を入れること。
・絵文字を使い、Threadsで目に留まりやすい魅力的な構成にすること。"""
    
    contents = [prompt, image] if image else prompt
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=contents)
        return response.text
    except Exception as e:
        return f"AI文章生成エラー: {e}"

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
    if not g_json: return False
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(g_json), scopes=scopes)
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row)
        return True
    except Exception as e:
        st.error(f"スプレッドシート保存エラー: {e}")
        return False

# ==========================================
# 🖥️ メインUI
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"", "rakuten_key":"", "gemini":"", "threads":"", "sheet_id":"", "g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "4. API設定"])

# --- API設定 ---
if page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード"):
        pw = st.text_input("合言葉", type="password")
        if st.button("自分のキーをロード"):
            if pw == st.secrets.get("master_password", "admin123"):
                st.session_state["api_keys"] = {
                    "rakuten_id": st.secrets.get("rakuten_id", ""), "rakuten_key": st.secrets.get("rakuten_key", ""),
                    "gemini": st.secrets.get("gemini_key", ""), "threads": st.secrets.get("threads_token", ""),
                    "sheet_id": st.secrets.get("sheet_id", ""), "g_json": st.secrets.get("g_json", "")
                }
                st.success("ロード成功！保存ボタンを押して有効化してください。")

    with st.container(border=True):
        api = st.session_state["api_keys"]
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天 App ID", value=api["rakuten_id"], type="password", key="r_id_final")
        r_key = c1.text_input("楽天 Access Key", value=api["rakuten_key"], type="password", key="r_key_final")
        g_key = c1.text_input("Gemini API Key", value=api["gemini"], type="password", key="g_key_final")
        t_tok = c2.text_input("Threads Token", value=api["threads"], type="password", key="t_tok_final")
        s_id = c2.text_input("Spreadsheet ID", value=api["sheet_id"], key="s_id_final")
        g_js = c2.text_area("Service Account JSON", value=api["g_json"], height=100, key="g_js_final")
        if st.button("設定を保存してツールを有効化"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("保存完了！")

# --- メイン機能 ---
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約投稿")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]: st.warning("API設定を完了させてください。")
    else:
        with st.container(border=True):
            st.subheader("STEP 1: ジャンル選択")
            # 🌟 楽天の全ジャンルを網羅したリスト
            genres_dict = {
                "🏆 総合ランキング": "0",
                "👗 レディースファッション": "100371",
                "👔 メンズファッション": "551177",
                "👜 バッグ・小物・ブランド雑貨": "216129",
                "👟 靴": "558885",
                "⌚ 腕時計": "558929",
                "💎 ジュエリー・アクセサリー": "200162",
                "💄 美容・コスメ・香水": "100939",
                "💊 ダイエット・健康": "100143",
                "🏥 医薬品・コンタクト・介護": "551169",
                "🍎 食品": "100227",
                "🍪 スイーツ・お菓子": "551167",
                "🍹 水・ソフトドリンク": "100316",
                "🍺 ビール・洋酒": "510915",
                "🍶 日本酒・焼酎": "510901",
                "🛋 インテリア・寝具・収納": "100804",
                "🍳 キッチン・食器・調理器具": "558944",
                "🧼 日用品・文房具・手芸": "215783",
                "🔌 家電": "562631",
                "📸 TV・オーディオ・カメラ": "211742",
                "💻 パソコン・周辺機器": "100026",
                "📱 スマフォ・タブレット": "562637",
                "⚽ スポーツ・アウトドア": "101070",
                "⛳ ゴルフ用品": "101077",
                "🚗 車・バイク用品": "503190",
                "🧸 おもちゃ": "101164",
                "🎨 ホビー": "101165",
                "🎸 楽器・音響機器": "112493",
                "🐱 ペット・ペットグッズ": "101213",
                "🍼 キッズ・ベビー・マタニティ": "100533",
                "📚 本・雑誌・コミック": "200376",
                "📀 CD・DVD": "101240",
                "🎮 TVゲーム": "101205"
            }
            sel_genre = st.selectbox("ランキングを取得したいジャンルを選択", list(genres_dict.keys()), key="full_genre_sel")
            if st.button("ランキングを読み込む"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], genres_dict[sel_genre])

        if "items" in st.session_state:
            st.subheader("STEP 2: 商品選択 ＆ 参考画像")
            selected = []
            for i, item in enumerate(st.session_state["items"]):
                with st.container(border=True):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    c2.write(f"**{item['itemName'][:60]}...**")
                    c2.write(f"価格: {item['itemPrice']}円")
                    if c2.checkbox("この商品を選ぶ", key=f"s_{i}"):
                        img = c2.file_uploader("参考画像(任意)", type=["jpg","png"], key=f"u_{i}")
                        item["user_img"] = img
                        selected.append(item)
            
            if selected:
                st.divider()
                st.subheader("STEP 3: ターゲット・文字数・トーン")
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1: gender = st.radio("性別", ["女性", "男性", "指定なし"], key="g_final")
                    with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="a_final")
                    with c3: kids = st.radio("家族構成", ["指定なし", "未就学児あり", "小学生あり"], key="k_final")
                    
                    tone = st.selectbox("文章のトーン", ["エモい", "役立つ", "共感", "元気"], key="tone_final")
                    char_len = st.slider("文字数の目安", 50, 500, 150, step=10, key="len_final")
                    
                    if st.button(f"✨ {len(selected)}件の文章を生成"):
                        target_str = f"{gender}, 年代:{','.join(age)}, 子供:{kids}"
                        res = []
                        pb = st.progress(0, text="AIが作成中...")
                        for j, s_item in enumerate(selected):
                            img_obj = Image.open(s_item["user_img"]) if s_item["user_img"] else None
                            txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], target_str, tone, char_len, api["gemini"], img_obj)
                            res.append({"item": s_item, "text": txt})
                            pb.progress((j+1)/len(selected))
                        st.session_state["final_posts"] = res

        if "final_posts" in st.session_state:
            st.subheader("STEP 4: 最終確認 ＆ 予約登録")
            for k, p in enumerate(st.session_state["final_posts"]):
                item = p["item"]
                with st.expander(f"編集: {item['itemName'][:30]}", expanded=True):
                    f_txt = st.text_area("本文", value=p["text"], key=f"ft_{k}", height=150)
                    use_img = st.checkbox("商品画像を添付", value=True, key=f"ui_{k}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 即時投稿", key=f"n_{k}"):
                        i_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                        mid = post_to_threads(api["threads"], f_txt, image_url=i_url)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], f"▼ 詳細はこちら\n{item['itemUrl']}", reply_to_id=mid)
                            st.success("成功！")
                    
                    with c_sch:
                        d = st.date_input("予約日", key=f"d_{k}")
                        t = st.time_input("時間", key=f"t_{k}")
                        if st.button("🗓️ 予約リストに追加", key=f"s_{k}"):
                            # NO, 本文, 投稿日, 時, 分, 投稿チェック, 投稿URL, ドライブURL, 返信, 画像URL
                            row = ["", f_txt, d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", f"▼ 詳細はこちら\n{item['itemUrl']}", item["mediumImageUrls"][0]["imageUrl"] if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                st.success("予約完了しました！")

elif page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
