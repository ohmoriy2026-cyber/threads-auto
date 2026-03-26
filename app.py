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
# 🎨 ページ全体の設定とカスタムCSS
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide")

st.markdown("""
<style>
    /* ページ全体の背景 */
    .stApp, .main { background-color: #1A1A1D !important; }

    /* サイドバーのデザイン */
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }

    /* 各ブロックの枠（STEPごと） */
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #26262B !important; 
        border: 1px solid #3A3A40 !important; 
        border-radius: 12px; 
        padding: 20px;
    }

    /* 🌟 【ここを修正】入力欄（テキストボックス・エリア）のデザイン */
    .stTextInput div[data-baseweb="input"], .stTextArea div[data-baseweb="textarea"] {
        background-color: #121214 !important; /* 真っ白から深い黒に変更 */
        border: 1px solid #4A4A55 !important; /* 控えめな枠線 */
        border-radius: 8px;
        color: #FFFFFF !important;
    }
    
    /* 入力欄にカーソルを合わせた時の色（Cyan） */
    .stTextInput div[data-baseweb="input"]:focus-within, .stTextArea div[data-baseweb="textarea"]:focus-within {
        border-color: #00E5FF !important;
        box-shadow: 0 0 0 1px #00E5FF !important;
    }

    /* 入力中の文字色 */
    .stTextInput input, .stTextArea textarea {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    /* ラベル文字（項目名）の色 */
    .stMarkdown, .stText, h1, h2, h3, p, label { color: #F0F0F0 !important; }

    /* ボタンのデザイン */
    .stButton>button { 
        background-color: #00E5FF !important; 
        color: #000000 !important; 
        font-weight: bold; 
        border-radius: 8px; 
        border: none; 
        transition: all 0.3s; 
    }
    .stButton>button:hover { 
        background-color: #00B8CC !important; 
        transform: scale(1.01);
        box-shadow: 0 4px 15px rgba(0, 229, 255, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 裏側の処理（関数）
# ==========================================

def get_rakuten_ranking(app_id, access_key, genre_id):
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": app_id, "accessKey": access_key, "genreId": genre_id}
    headers = {"Referer": "https://localhost/"}
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return [item["Item"] for item in response.json().get("Items", [])[:10]]
        st.error(f"❌ 楽天APIエラー: {response.text}")
    except Exception as e:
        st.error(f"❌ 通信エラー: {e}")
    return []

def generate_post_text(item_name, price, target_details, tone, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"""あなたは優秀なSNSマーケターです。以下の楽天商品を紹介するThreads用の投稿文を作成してください。
【商品】{item_name} / {price}円
【ターゲット】{target_details}
【トーン】{tone}
【条件】
・絵文字を使って親しみやすく短く。最後に「詳細はこちら👇」と入れること。
・【重要】「はい、承知いたしました」などの挨拶、返事、前置きは一切書かず、本文のみを出力すること。"""
    contents = [prompt, image] if image else prompt
    response = client.models.generate_content(model='gemini-2.5-flash', contents=contents)
    return response.text

def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    create_url = "https://graph.threads.net/v1.0/me/threads"
    params = {"access_token": access_token, "text": text}
    params["media_type"] = "IMAGE" if image_url else "TEXT"
    if image_url: params["image_url"] = image_url
    if reply_to_id: params["reply_to_id"] = reply_to_id
    
    res = requests.post(create_url, params=params)
    if res.status_code == 200:
        creation_id = res.json().get("id")
        # 画像投稿時はステータスがFINISHEDになるまで待機（最大30秒）
        if image_url:
            check_url = f"https://graph.threads.net/v1.0/{creation_id}"
            for _ in range(6):
                time.sleep(5)
                status = requests.get(check_url, params={"access_token": access_token, "fields": "status"}).json()
                if status.get("status") == "FINISHED": break
        
        # 公開
        pub_res = requests.post("https://graph.threads.net/v1.0/me/threads_publish", params={"access_token": access_token, "creation_id": creation_id})
        return pub_res.json().get("id") if pub_res.status_code == 200 else None
    return None

def save_to_sheets(sheet_id, service_account_json, data):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(service_account_json), scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        sheet.append_row(data)
        return True
    except Exception as e:
        st.error(f"❌ スプレッドシート保存エラー: {e}")
        return False

# ==========================================
# 🖥️ セッション初期化
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {
        "rakuten_id": "", "rakuten_key": "", "gemini": "", "threads": "", "sheet_id": "", "g_json": ""
    }

st.sidebar.title("📱 メニュー")
page = st.sidebar.radio("ページを選択", ["1. ダッシュボード", "2. 商品作成＆投稿予約", "4. API設定"])

# ------------------------------------------
# ページ4: API設定（他人のキーは見せない）
# ------------------------------------------
if page == "4. API設定":
    st.title("⚙️ API設定")
    st.info("APIキーはブラウザを閉じると消去されます。")
    
    # 🌟 管理者用一括ロード機能
    with st.expander("👤 管理者モード"):
        master_pw = st.text_input("合言葉を入力", type="password")
        if st.button("自分のキーを自動入力"):
            if master_pw == st.secrets.get("master_password", "admin123"):
                st.session_state["api_keys"] = {
                    "rakuten_id": st.secrets.get("rakuten_id", ""),
                    "rakuten_key": st.secrets.get("rakuten_key", ""),
                    "gemini": st.secrets.get("gemini_key", ""),
                    "threads": st.secrets.get("threads_token", ""),
                    "sheet_id": st.secrets.get("sheet_id", ""),
                    "g_json": st.secrets.get("g_json", "")
                }
                st.success("✅ 管理者キーをロードしました。下の保存ボタンを押してください。")
            else:
                st.error("合言葉が違います")

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            r_id = st.text_input("楽天 App ID", value=st.session_state["api_keys"]["rakuten_id"], type="password")
            r_key = st.text_input("楽天 Access Key", value=st.session_state["api_keys"]["rakuten_key"], type="password")
            g_key = st.text_input("Gemini API Key", value=st.session_state["api_keys"]["gemini"], type="password")
        with col2:
            t_tok = st.text_input("Threads Token", value=st.session_state["api_keys"]["threads"], type="password")
            s_id = st.text_input("Spreadsheet ID", value=st.session_state["api_keys"]["sheet_id"])
            g_json = st.text_area("Google Service Account JSON", value=st.session_state["api_keys"]["g_json"], height=100)

        if st.button("設定を保存してツールを有効化"):
            st.session_state["api_keys"].update({
                "rakuten_id": r_id, "rakuten_key": r_key, "gemini": g_key, 
                "threads": t_tok, "sheet_id": s_id, "g_json": g_json
            })
            st.success("✅ 設定を完了しました！")

# ------------------------------------------
# ページ2: 商品作成＆投稿予約
# ------------------------------------------
elif page == "2. 商品作成＆投稿予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]:
        st.warning("⚠️ 「API設定」からキーを入力してください。")
    else:
        # STEP 1: ランキング
        with st.container(border=True):
            genres = {"総合": "0", "レディース": "100371", "メンズ": "551177", "家電": "211742", "美容": "100939"}
            genre_name = st.selectbox("ジャンル選択", list(genres.keys()))
            if st.button("ランキングを取得"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], genres[genre_name])

        if "items" in st.session_state:
            st.subheader("STEP 2: 商品選択 ＆ AI執筆")
            selected_items = []
            for i, item in enumerate(st.session_state["items"]):
                with st.container(border=True):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    c2.write(f"**{item['itemName'][:50]}...**")
                    if c2.checkbox("この商品を選ぶ", key=f"chk_{i}"):
                        up_img = c2.file_uploader("参考画像(任意)", type=["jpg","png"], key=f"up_{i}")
                        item["temp_img"] = up_img
                        selected_items.append(item)
            
            if selected_items:
                st.divider()
                t1, t2, t3 = st.columns(3)
                target = t1.text_input("ターゲット", "20代女性、共感重視")
                tone = t2.selectbox("トーン", ["エモい", "役立つ", "ハイテンション"])
                if t3.button(f"✨ {len(selected_items)}件の文章を作成"):
                    res_posts = []
                    pb = st.progress(0)
                    for j, s_item in enumerate(selected_items):
                        pil_img = Image.open(s_item["temp_img"]) if s_item["temp_img"] else None
                        txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], target, tone, api["gemini"], pil_img)
                        res_posts.append({"item": s_item, "text": txt})
                        pb.progress((j+1)/len(selected_items))
                    st.session_state["generated_posts"] = res_posts

        if "generated_posts" in st.session_state:
            st.subheader("STEP 3: 最終確認 ＆ 予約投稿")
            for k, p_data in enumerate(st.session_state["generated_posts"]):
                item = p_data["item"]
                with st.expander(f"編集: {item['itemName'][:30]}"):
                    final_txt = st.text_area("本文", value=p_data["text"], key=f"f_txt_{k}")
                    use_img = st.checkbox("商品画像を添付する", value=True, key=f"u_img_{k}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 今すぐ投稿", key=f"btn_n_{k}"):
                        img_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                        res_id = post_to_threads(api["threads"], final_txt, image_url=img_url)
                        if res_id:
                            time.sleep(5)
                            post_to_threads(api["threads"], f"▼ 詳細はこちら\n{item['itemUrl']}", reply_to_id=res_id)
                            st.success("投稿完了！")
                    
                    with c_sch:
                        sch_d = st.date_input("予約日", key=f"d_{k}")
                        sch_t = st.time_input("予約時間", key=f"t_{k}")
                        if st.button("🗓️ 予約リストに追加", key=f"btn_s_{k}"):
                            if not api["sheet_id"] or not api["g_json"]:
                                st.error("API設定でスプレッドシート情報を入力してください")
                            else:
                                dt_str = f"{sch_d} {sch_t}"
                                img_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else ""
                                row = [dt_str, item["itemName"], item["itemUrl"], img_url, final_txt, "pending"]
                                if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                    st.success(f"予約完了: {dt_str}")

elif page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    st.write("スプレッドシートと連携して、ここに予約状況を表示する機能を今後追加予定です。")
