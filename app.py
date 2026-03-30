import streamlit as st
import requests
from google import genai
import time
from PIL import Image
import io
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import concurrent.futures
import re
import urllib.parse

# ==========================================
# 🎨 デザイナー設計：モダンUI
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display: none;}
    .stApp { font-family: 'Helvetica Neue', Arial, sans-serif; }
    [data-testid="stVerticalBlockBorderWrapper"] { 
        border-radius: 12px; padding: 20px; margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); background-color: #ffffff;
    }
    .stButton>button { 
        background-color: #007AFF !important; color: #FFFFFF !important; font-weight: bold; 
        border-radius: 8px; width: 100%; border: none; padding: 0.6rem 1rem;
    }
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; font-weight: 800 !important; color: #007AFF !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群
# ==========================================

def convert_drive_link(url):
    """Googleドライブの共有リンクを直リンクに変換する"""
    if "drive.google.com" not in url:
        return url
    try:
        # IDを抽出
        if "file/d/" in url:
            file_id = url.split("file/d/")[1].split("/")[0]
        elif "id=" in url:
            file_id = url.split("id=")[1].split("&")[0]
        else:
            return url
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    except:
        return url

def download_image(url):
    try:
        res = requests.get(url, timeout=10)
        return Image.open(io.BytesIO(res.content))
    except: return None

def save_to_sheets(sheet_id, g_json, row_data):
    try:
        creds_dict = json.loads(g_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except: return False

def get_sheet_data(sheet_id, g_json):
    try:
        creds_dict = json.loads(g_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        data = client.open_by_key(sheet_id).sheet1.get_all_values()
        return [dict(zip(data[0], row)) for row in data[1:] if any(row)]
    except: return []

def get_templates(sheet_id, g_json):
    try:
        creds_dict = json.loads(g_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        ss = client.open_by_key(sheet_id)
        ws = ss.worksheet("テンプレート")
        data = ws.get_all_values()
        return [{"title": row[0], "content": row[1]} for row in data[1:] if len(row) >= 2 and row[0]]
    except: return []

def get_threads_engagement(token):
    if not token: return []
    url = f"https://graph.threads.net/v1.0/me/threads?fields=id,text,timestamp,is_reply&limit=100&access_token={token}"
    try:
        res = requests.get(url).json()
        threads = res.get("data", [])
        def fetch_insights(t):
            ins_url = f"https://graph.threads.net/v1.0/{t['id']}/insights?metric=views,likes,replies&access_token={token}"
            try:
                ins_res = requests.get(ins_url).json()
                metrics = {d['name']: d['values'][0]['value'] for d in ins_res.get("data", [])}
                t.update({'views': metrics.get('views', 0), 'likes': metrics.get('likes', 0), 'replies': metrics.get('replies', 0)})
            except: t.update({'views': 0, 'likes': 0, 'replies': 0})
            return t
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            return list(executor.map(fetch_insights, threads))
    except: return []

def get_rakuten_ranking(app_id, access_key, affiliate_id, genre_id):
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": app_id, "accessKey": access_key, "genreId": genre_id}
    if affiliate_id: params["affiliateId"] = affiliate_id
    try:
        res = requests.get(url, params=params).json()
        return [item["Item"] for item in res.get("Items", [])[:10]]
    except: return []

def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"楽天商品「{item_name}」をターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介。画像解析も重視。本文のみ。"
    if reference_post: prompt += f"\n\n【参考】\n{reference_post}"
    if custom_prompt: prompt += f"\n\n【指示】\n{custom_prompt}"
    contents = [prompt, image] if image else prompt
    return client.models.generate_content(model='gemini-2.0-flash', contents=contents).text

def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    url = "https://graph.threads.net/v1.0/me/threads"
    params = {"access_token": access_token, "text": text, "media_type": "IMAGE" if image_url else "TEXT"}
    if image_url: params["image_url"] = image_url
    if reply_to_id: params["reply_to_id"] = reply_to_id
    try:
        res = requests.post(url, params=params).json()
        c_id = res.get("id")
        if c_id:
            if image_url: time.sleep(10)
            requests.post("https://graph.threads.net/v1.0/me/threads_publish", params={"access_token": access_token, "creation_id": c_id})
            return c_id
    except: pass
    return None

# ==========================================
# 🖥️ メイン
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"","rakuten_key":"","rakuten_aff_id":"","gemini":"","threads":"","sheet_id":"","g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. 分析", "4. API設定", "5. テンプレート管理"])

# ------------------------------------------
# 📊 1. ダッシュボード
# ------------------------------------------
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    api = st.session_state["api_keys"]
    if api["threads"]:
        raw = get_threads_engagement(api["threads"])
        if raw:
            df = pd.DataFrame(raw)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("累計投稿", len(df)); st.bar_chart(df.groupby('timestamp').size())
            with c2: st.metric("累計いいね", df['likes'].sum()); st.bar_chart(df.groupby('timestamp')['likes'].sum(), color="#FF4B4B")
            with c3: st.metric("累計返信", df['replies'].sum()); st.bar_chart(df.groupby('timestamp')['replies'].sum(), color="#FFB800")

# ------------------------------------------
# 🛒 2. 商品作成＆予約 (判別ロジック搭載)
# ------------------------------------------
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    if not api["gemini"]: st.warning("API設定を完了してください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキング", "🔗 URLから", "📸 画像から"])

        def common_ui(k):
            c1, c2, c3 = st.columns(3)
            with c1: gen = st.radio("性別", ["女性", "男性", "指定なし"], key=f"g_{k}")
            with c2: age = st.multiselect("年代", ["20代", "30代", "40代"], default=["20代"], key=f"a_{k}")
            with c3: kids = st.radio("子供", ["なし", "あり"], key=f"k_{k}")
            tone = st.selectbox("トーン", ["エモい", "役立つ", "親近感"], key=f"t_{k}")
            len_val = st.slider("文字数", 50, 400, 80, key=f"l_{k}")
            tmp_opt = ["手動"] + [t["title"] for t in templates]
            sel_tmp = st.selectbox("テンプレート", tmp_opt, key=f"tmp_{k}")
            ref = next((t["content"] for t in templates if t["title"] == sel_tmp), "") if sel_tmp != "手動" else ""
            ref_post = st.text_area("参考投稿", value=ref, key=f"ra_{k}")
            custom = st.text_area("自由指示", key=f"cp_{k}")
            return f"{gen}, {age}, 子供:{kids}", tone, len_val, ref_post, custom

# ------------------------------------
        # タブ1：ランキングから探す
        # ------------------------------------
        with tab1:
　　　　　　　st.write("人気のランキングから商品を一括で探して作成します。")
            with st.container(border=True):
                genres_dict = {
                    "🏆 総合ランキング": "0", "👗 レディースファッション": "100371", "👔 メンズファッション": "551177",
                    "👜 バッグ・小物・ブランド雑貨": "216129", "👟 靴": "558885", "⌚ 腕時計": "558929",
                    "💎 ジュエリー・アクセサリー": "200162", "💄 美容・コスメ・香水": "100939", "💊 ダイエット・健康": "100143",
                    "🏥 医薬品・コンタクト・介護": "551169", "🍎 食品": "100227", "🍪 スイーツ・お菓子": "551167",
                    "🍹 水・ソフトドリンク": "100316", "🍺 ビール・洋酒": "510915", "🍶 日本酒・焼酎": "510901",
                    "🛋 インテリア・寝具・収納": "100804", "🍳 キッチン・食器・調理器具": "558944", "🧼 日用品・文房具・手芸": "215783",
                    "🔌 家電": "562631", "📸 TV・オーディオ・カメラ": "211742", "💻 パソコン・周辺機器": "100026",
                    "📱 スマフォ・タブレット": "562637", "⚽ スポーツ・アウトドア": "101070", "⛳ ゴルフ用品": "101077",
                    "🚗 車・バイク用品": "503190", "🧸 おもちゃ": "101164", "🎨 ホビー": "101165",
                    "🎸 楽器・音響機器": "112493", "🐱 ペット・ペットグッズ": "101213", "🍼 キッズ・ベビー・マタニティ": "100533",
                    "📚 本・雑誌・コミック": "200376", "📀 CD・DVD": "101240", "🎮 TVゲーム": "101205",
                    "🔧 その他 (ID指定)": "custom"
                }
                sel_name = st.selectbox("ランキングを取得したいジャンルを選択", list(genres_dict.keys()), key="sel_genre_p1")
            
            if "items" in st.session_state:
                selected = []
                for i, item in enumerate(st.session_state["items"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        c2.write(f"**{item['itemName'][:50]}**")
                        if c2.checkbox("選ぶ", key=f"chk_{i}"):
                            # AI解析用の画像アップローダー
                            u_f = c2.file_uploader("📸 スクショ添付 (AI解析用)", type=["jpg","png"], key=f"uf_{i}")
                            item["user_file"] = u_f
                            selected.append(item)
                
                if selected:
                    st.divider(); t_str, tone, length, ref, custom = common_ui("t1")
                    if st.button(f"✨ {len(selected)}件の文章を一括生成"):
                        res_list = []
                        for it in selected:
                            # AI解析: 自分のスクショがあれば優先、なければ楽天画像
                            ana_img = Image.open(it["user_file"]) if it["user_file"] else download_image(it["mediumImageUrls"][0]["imageUrl"])
                            txt = generate_post_text(it["itemName"], it["itemPrice"], t_str, tone, length, custom, ref, api["gemini"], image=ana_img)
                            res_list.append({"item": it, "text": txt})
                        st.session_state["gen_res"] = res_list

            if "gen_res" in st.session_state:
                for k, res in enumerate(st.session_state["gen_res"]):
                    with st.expander(f"確認: {res['item']['itemName'][:30]}", expanded=True):
                        it = res["item"]
                        # --- 💡 画像判別ロジックのUI ---
                        use_img = st.checkbox("🖼️ 投稿に画像を含める", value=True, key=f"use_img_{k}")
                        drive_url = st.text_input("🔗 投稿用画像URL (Googleドライブ等: 空なら楽天画像を引用)", key=f"drive_{k}")
                        
                        m_k, r_k = f"m_{k}", f"r_{k}"
                        if m_k not in st.session_state: st.session_state[m_k] = res["text"]
                        if r_k not in st.session_state: st.session_state[r_k] = f"▼ 詳細はこちら\n{it.get('affiliateUrl', it['itemUrl'])}"
                        
                        m_txt = st.text_area("本文", key=m_k, height=150)
                        r_txt = st.text_area("リプライ", key=r_k, height=80)
                        
                        if st.button("🚀 即時投稿", key=f"now_{k}"):
                            # 投稿画像URLの決定
                            final_img = None
                            if use_img:
                                final_img = convert_drive_link(drive_url) if drive_url else it["mediumImageUrls"][0]["imageUrl"]
                            
                            mid = post_to_threads(api["threads"], m_txt, image_url=final_img)
                            if mid:
                                time.sleep(5); post_to_threads(api["threads"], r_txt, reply_to_id=mid); st.success("成功")
                        
                        d_v, t_v = st.date_input("予約日", key=f"d_{k}"), st.time_input("時間", key=f"t_{k}")
                        if st.button("🗓️ 予約追加", key=f"res_{k}"):
                            final_img = convert_drive_link(drive_url) if (use_img and drive_url) else (it["mediumImageUrls"][0]["imageUrl"] if use_img else "")
                            row = ["", m_txt, d_v.strftime('%Y/%m/%d'), str(t_v.hour), str(t_v.minute), "pending", "", "", r_txt, final_img]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row): st.success("保存完了")

# ------------------------------------------
# その他のページは以前と同様
# ------------------------------------------
elif page == "3. 分析":
    st.title("🔍 週次分析")
    api = st.session_state["api_keys"]
    if api["threads"]:
        raw = get_threads_engagement(api["threads"])
        if raw:
            df = pd.DataFrame(raw)
            st.metric("今週の閲覧数", f"{df['views'].sum():,}")
            st.dataframe(df, use_container_width=True)

elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 ロード"):
        pw = st.text_input("合言葉", type="password")
        if st.button("読み込み"):
            if pw == st.secrets.get("master_password"):
                for k, sk in zip(["api_ri","api_rk","api_ra","api_gk","api_tt","api_si","api_gj"], ["rakuten_id","rakuten_key","rakuten_aff_id","gemini_key","threads_token","sheet_id","g_json"]):
                    st.session_state[k] = st.secrets.get(sk, "")
                st.success("完了！保存を押してください")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天ID", key="api_ri", type="password")
        r_key = c1.text_input("楽天Key", key="api_rk", type="password")
        r_aff = c1.text_input("楽天Aff", key="api_ra", type="password")
        g_key = c2.text_input("Gemini API", key="api_gk", type="password")
        t_tok = c2.text_input("Threads Token", key="api_tt", type="password")
        s_id = c2.text_input("Sheet ID", key="api_si")
        g_js = st.text_area("JSON", key="api_gj", height=100)
        if st.button("保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "rakuten_aff_id":r_aff, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("完了")

elif page == "5. テンプレート管理":
    st.title("📝 テンプレート")
    api = st.session_state["api_keys"]
    if api["sheet_id"]:
        with st.form("tm"):
            ti = st.text_input("タイトル"); co = st.text_area("型")
            if st.form_submit_button("保存"):
                if save_template(api["sheet_id"], api["g_json"], ti, co): st.success("成功"); st.rerun()
        for t in get_templates(api["sheet_id"], api["g_json"]):
            with st.expander(t["title"]): st.write(t["content"])
