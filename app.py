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
# ⚙️ 関数群（ご提示のロジックを完全反映）
# ==========================================

def convert_drive_link(url):
    if not url or "drive.google.com" not in url: return url
    try:
        if "file/d/" in url: file_id = url.split("file/d/")[1].split("/")[0]
        elif "id=" in url: file_id = url.split("id=")[1].split("&")[0]
        else: return url
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    except: return url

def download_image(url):
    if not url: return None
    try:
        target_url = convert_drive_link(url)
        res = requests.get(target_url, timeout=10)
        return Image.open(io.BytesIO(res.content))
    except: return None

def save_to_sheets(sheet_id, g_json, row_data):
    if not sheet_id or not g_json: return False
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gspread.authorize(creds).open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except: return False

def get_sheet_data(sheet_id, g_json):
    if not sheet_id or not g_json: return []
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        data = gspread.authorize(creds).open_by_key(sheet_id).sheet1.get_all_values()
        if len(data) < 2: return []
        return [dict(zip(data[0], row)) for row in data[1:] if any(row)]
    except: return []

def get_templates(sheet_id, g_json):
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        ws = gspread.authorize(creds).open_by_key(sheet_id).worksheet("テンプレート")
        data = ws.get_all_values()
        return [{"title": row[0], "content": row[1]} for row in data[1:] if len(row) >= 2 and row[0]]
    except: return []

def get_threads_engagement(token):
    if not token: return []
    try:
        res = requests.get(f"https://graph.threads.net/v1.0/me/threads?fields=id,text,timestamp,is_reply&limit=100&access_token={token}").json()
        threads = res.get("data", [])
        def fetch_insights(th):
            try:
                data = requests.get(f"https://graph.threads.net/v1.0/{th['id']}/insights?metric=views,likes,replies&access_token={token}").json().get("data", [])
                m = {d.get('name'): (d.get('values', [{}])[0].get('value', 0)) for d in data}
                th.update({'views': m.get('views',0), 'like_count': m.get('likes',0), 'reply_count': m.get('replies',0)})
            except: th.update({'views':0, 'like_count':0, 'reply_count':0})
            return th
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            return list(executor.map(fetch_insights, threads))
    except: return []

def get_rakuten_ranking(app_id, access_key, affiliate_id, genre_id):
    if not app_id or not access_key: return []
    params = {"applicationId": str(app_id).strip(), "accessKey": str(access_key).strip(), "genreId": str(genre_id).strip()}
    if affiliate_id: params["affiliateId"] = str(affiliate_id).strip()
    try:
        res = requests.get("https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601", params=params).json()
        return [item["Item"] for item in res.get("Items", [])[:10]]
    except: return []

# --- 💡 ご提示のロジックを反映したAI生成関数 ---
def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    if not api_key: return "❌ APIキー未設定"
    prompt = f"楽天商品「{item_name}」({price}円)をターゲット【{target_str}】へ{tone}なテイストで約{length}文字で紹介して。\n"
    prompt += "条件:挨拶不要、URL誘導文禁止、人間味のあるリアルな言葉、好奇心を煽るフック必須。\n"
    if reference_post: prompt += f"参考投稿内容: {reference_post}\n"
    prompt += f"特別指示:{custom_prompt}"
    
    try:
        # ご提示のClient形式。404が出る場合は 'gemini-1.5-flash' に書き換えてください。
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.0-flash', # 最新の2.0を推奨、必要に応じて変更可
            contents=[prompt, image] if image else prompt
        )
        return response.text
    except Exception as e:
        return f"❌ AIエラー: {e}"

# --- 💡 ご提示のロジックを反映した投稿関数 ---
def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    params = {"access_token": access_token, "text": text, "media_type": "IMAGE" if image_url else "TEXT"}
    if image_url: params["image_url"] = image_url
    if reply_to_id: params["reply_to_id"] = reply_to_id
    try:
        res = requests.post("https://graph.threads.net/v1.0/me/threads", params=params)
        if res.status_code == 200:
            c_id = res.json().get("id")
            if image_url: time.sleep(10)
            requests.post("https://graph.threads.net/v1.0/me/threads_publish", params={"access_token": access_token, "creation_id": c_id})
            return c_id
    except: pass
    return None

# ==========================================
# 🖥️ サイドバー & メイン
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"","rakuten_key":"","rakuten_aff_id":"","gemini":"","threads":"","sheet_id":"","g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. 分析", "4. API設定", "5. テンプレート管理"])
tone_list = ["エモい", "役立つ", "元気", "親近感", "本音レビュー風", "あざと可愛い", "高級感"]

# ------------------------------------------
# 📊 1. ダッシュボード (日付 m/d形式)
# ------------------------------------------
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    api = st.session_state["api_keys"]
    if api["threads"]:
        with st.spinner("データを取得中..."):
            raw = get_threads_engagement(api["threads"])
            if raw:
                df = pd.DataFrame(raw)
                df['date_key'] = pd.to_datetime(df['timestamp']).dt.strftime('%m/%d')
                c1, c2, c3 = st.columns(3)
                with c1: st.metric("累計投稿", len(df)); st.bar_chart(df.groupby('date_key').size())
                with c2: st.metric("累計いいね", df['like_count'].sum()); st.bar_chart(df.groupby('date_key')['like_count'].sum(), color="#FF4B4B")
                with c3: st.metric("累計返信", df['reply_count'].sum()); st.bar_chart(df.groupby('date_key')['reply_count'].sum(), color="#FFB800")
                st.divider(); st.subheader("📅 本日の予定")
                s_data = get_sheet_data(api["sheet_id"], api["g_json"])
                today = datetime.now().strftime('%Y/%m/%d')
                t_list = [r for r in s_data if r.get('投稿日') == today]
                if t_list: st.dataframe(pd.DataFrame(t_list)[['時', '分', '本文']], use_container_width=True)
                else: st.success("予定はありません")

# ------------------------------------------
# 🛒 2. 商品作成＆予約
# ------------------------------------------
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    if not api["gemini"]: st.warning("API設定を先に済ませてください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキングから", "🔗 URLから", "📸 画像から"])

        def draw_ui(k):
            c1, c2, c3 = st.columns(3)
            with c1: gen = st.radio("性別", ["女性", "男性", "指定なし"], key=f"g_{k}")
            with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key=f"a_{k}")
            with c3: kids = st.radio("子供", ["なし", "あり"], key=f"k_{k}")
            tone = st.selectbox("トーン", tone_list, key=f"t_{k}")
            length = st.slider("文字数", 30, 400, 80, key=f"l_{k}")
            sel = st.selectbox("テンプレート", ["手動入力"] + [t["title"] for t in templates], key=f"tmp_{k}")
            ref = next((t["content"] for t in templates if t["title"] == sel), "") if sel != "手動入力" else ""
            ref_p = st.text_area("参考本文", value=ref, key=f"ra_{k}", height=100)
            cp = st.text_area("追加指示", key=f"cp_{k}", height=70)
            return f"{gen}, {age}, 子供:{kids}", tone, length, ref_p, cp

        def show_final(key, d_url, d_img):
            if key in st.session_state:
                p = st.session_state[key]
                with st.expander("✨ 投稿の最終確認・編集", expanded=True):
                    # 画像の有無チェックBOX完備
                    use_i = st.checkbox("🖼️ 投稿に画像を含める", value=True, key=f"ui_f_{key}")
                    dr_url = st.text_input("🔗 投稿用画像URL (Googleドライブ等: 空ならデフォルト引用)", value=d_img if d_img else "", key=f"dr_f_{key}")
                    mk, rk = f"m_f_{key}", f"r_f_{key}"
                    if mk not in st.session_state: st.session_state[mk] = p["text"]
                    if rk not in st.session_state: st.session_state[rk] = f"▼ 詳細はこちら\n{d_url}"
                    mt = st.text_area("本文", key=mk, height=150); rt = st.text_area("リプライ", key=rk, height=80)
                    
                    f_img = convert_drive_link(dr_url) if use_i and dr_url else (d_img if use_i else None)
                    cn, cs = st.columns(2)
                    if cn.button("🚀 即時投稿", key=f"now_b_{key}"):
                        mid = post_to_threads(api["threads"], st.session_state[mk], image_url=f_img)
                        if mid: time.sleep(5); post_to_threads(api["threads"], st.session_state[rk], reply_to_id=mid); st.success("投稿完了")
                    with cs:
                        dv, tv = st.date_input("日", key=f"df_{key}"), st.time_input("時", key=f"tf_{key}")
                        if st.button("🗓️ 予約登録", key=f"res_b_{key}"):
                            row = ["", st.session_state[mk], dv.strftime('%Y/%m/%d'), str(tv.hour), str(tv.minute), "pending", "", "", st.session_state[rk], f_img if f_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row): st.success("保存完了")

        with tab1:
            # 主要31ジャンル網羅リスト
            genres = {
                "🏆 総合": "0", "👗 レディース": "100371", "👔 メンズ": "551177", "👠 靴": "558885", 
                "👜 バッグ": "216129", "💄 美容": "100939", "💊 ダイエット": "100143", "🏥 医薬品": "551169",
                "🍎 食品": "100227", "🍪 スイーツ": "551167", "🍹 飲料": "100316", "🍺 洋酒": "510915", 
                "🍶 日本酒": "510901", "🛋 インテリア": "100804", "🍳 キッチン": "558944", "🚿 日用品": "215783",
                "🔌 家電": "562631", "📸 カメラ": "211742", "💻 パソコン": "100026", "⚽ スポーツ": "101070", 
                "⛳ ゴルフ": "101077", "🚗 車・バイク": "503190", "🧸 おもちゃ": "101164", "🎨 ホビー": "101165", 
                "🎸 楽器": "112493", "🎮 ゲーム": "101205", "🐱 ペット": "101213", "🍼 ベビー": "100533",
                "📚 本": "200376", "📀 CD・DVD": "101240", "💠 その他": "custom"
            }
            sel_g = st.selectbox("ジャンル選択", list(genres.keys()), key="rank_list_v_final")
            if st.button("ランキング取得"):
                st.session_state["it_v_final"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres[sel_g])
            
            if "it_v_final" in st.session_state:
                selected = []
                for i, it in enumerate(st.session_state["it_v_final"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(it["mediumImageUrls"][0]["imageUrl"])
                        if c2.checkbox(f"選ぶ: {it['itemName'][:50]}", key=f"chk_{i}"):
                            uf = c2.file_uploader(f"📸 スクショ添付 (任意)", type=["jpg","png"], key=f"uf_{i}")
                            it["user_file"] = uf; selected.append(it)
                if selected:
                    t_str, tone, length, ref, cp = draw_ui("tab1")
                    if st.button(f"✨ {len(selected)}件を一括生成"):
                        for it in selected:
                            ana = Image.open(it["user_file"]) if it["user_file"] else download_image(it["mediumImageUrls"][0]["imageUrl"])
                            txt = generate_post_text(it["itemName"], it.get("itemPrice",""), t_str, tone, length, cp, ref, api["gemini"], image=ana)
                            st.session_state[f"r1_{it['itemCode']}"] = {"text": txt}
                            show_final(f"r1_{it['itemCode']}", it["itemUrl"], it["mediumImageUrls"][0]["imageUrl"])

        with tab2:
            url_in = st.text_input("楽天URL貼り付け", key="u_in_tab2")
            if st.button("情報取得"):
                res = requests.get(url_in, headers={'User-Agent': 'Mozilla/5.0'}).text
                t_m = re.search(r'<title>(.*?)</title>', res, re.DOTALL)
                i_m = re.search(r'<meta\s+property="og:image"\s+content="(.*?)"', res)
                st.session_state["u_tab2"] = {"name": t_m.group(1)[:50] if t_m else "商品", "img": i_m.group(1) if i_m else "", "url": url_in}
            if "u_tab2" in st.session_state:
                u = st.session_state["u_tab2"]; st.image(u["img"], width=150); t_str, tone, length, ref, cp = draw_ui("tab2")
                if st.button("✨ 本文作成"):
                    st.session_state["res2_f"] = {"text": generate_post_text(u["name"], "", t_str, tone, length, cp, ref, api["gemini"], image=download_image(u["img"]))}
                show_final("res2_f", u["url"], u["img"])

        with tab3:
            # --- 💡 要望通りのフロー： URL ➡ 作成 ➡ 追加添付 ---
            img_url_t3 = st.text_input("🔗 画像URLを貼る (Googleドライブ等)", key="url_tab3")
            hint_t3 = st.text_input("商品名やヒント", key="hint_tab3")
            t_str, tone, length, ref, cp = draw_ui("tab3")
            if st.button("✨ 本文を作成"):
                st.session_state["res3_f"] = {"text": generate_post_text(hint_t3, "", t_str, tone, length, cp, ref, api["gemini"], image=download_image(img_url_t3))}
            if "res3_f" in st.session_state:
                uf_t3 = st.file_uploader("📸 投稿用スクショ添付 (無ければ上記URLを使用)", type=["jpg","png"], key="uf_t3")
                aff_t3 = st.text_input("🔗 アフィリエイトURL", key="aff_t3")
                show_final("res3_f", aff_t3, img_url_t3)

# ------------------------------------------
# 🔍 3. 分析
# ------------------------------------------
elif page == "3. 分析":
    st.title("🔍 週次分析")
    api = st.session_state["api_keys"]
    if api["threads"]:
        raw = get_threads_engagement(api["threads"])
        if raw:
            df = pd.DataFrame(raw); df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            today = datetime.now().date(); st_this = today - timedelta(days=today.weekday())
            this_df = df[df['timestamp'] >= st_this]
            c1, c2, c3, c4 = st.columns(4)
            # 文法エラーを改行して解消
            def get_delta(current, previous):
                return f"{current - previous}"
            
            c1.metric("今週の投稿", f"{len(this_df)} 件")
            c2.metric("今週の閲覧", f"{this_df['views'].sum():,}")
            c3.metric("今週のいいね", f"{this_df['like_count'].sum():,}")
            c4.metric("今週の返信", f"{this_df['reply_count'].sum():,}")
            st.divider(); st.dataframe(df.sort_values('views', ascending=False), use_container_width=True)

# ------------------------------------------
# ⚙️ 4. API設定 (管理者ロード)
# ------------------------------------------
elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード", expanded=True):
        pw = st.text_input("合言葉", type="password", key="apw")
        if st.button("Secretsからロード"):
            if pw == st.secrets.get("master_password"):
                st.session_state["api_ri"] = st.secrets.get("rakuten_id", ""); st.session_state["api_rk"] = st.secrets.get("rakuten_key", "")
                st.session_state["api_ra"] = st.secrets.get("rakuten_aff_id", ""); st.session_state["api_gk"] = st.secrets.get("gemini_key", "")
                st.session_state["api_tt"] = st.secrets.get("threads_token", ""); st.session_state["api_si"] = st.secrets.get("sheet_id", "")
                st.session_state["api_gj"] = st.secrets.get("g_json", ""); st.success("ロード完了！保存をクリック")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天ID", key="api_ri", type="password"); r_key = c1.text_input("楽天Key", key="api_rk", type="password"); r_aff = c1.text_input("楽天Aff", key="api_ra", type="password")
        g_key = c2.text_input("Gemini API", key="api_gk", type="password"); t_tok = c2.text_input("Threads Token", key="api_tt", type="password"); s_id = c2.text_input("Sheet ID", key="api_si")
        g_js = st.text_area("JSON", key="api_gj", height=100)
        if st.button("設定を保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "rakuten_aff_id":r_aff, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("完了")

elif page == "5. テンプレート管理":
    st.title("📝 テンプレート")
    api = st.session_state["api_keys"]
    if api["sheet_id"]:
        with st.form("tm"):
            ti = st.text_input("タイトル"); co = st.text_area("本文型", height=150)
            if st.form_submit_button("保存"):
                if save_template(api["sheet_id"], api["g_json"], ti, co): st.success("成功"); time.sleep(1); st.rerun()
        for t in get_templates(api["sheet_id"], api["g_json"]):
            with st.expander(t["title"]): st.write(t["content"])
