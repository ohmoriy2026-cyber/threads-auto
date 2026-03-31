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
from streamlit_local_storage import LocalStorage

# ==========================================
# 🎨 デザイナー設計：モダンUI ＆ ヘッダー調整
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* 右上の不要なアイコン群だけを消し、左のサイドバー開閉「＞」は残す */
    [data-testid="stHeaderActionElements"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    .stAppDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    header { visibility: visible !important; background: transparent !important; }

    .stApp { font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif; }
    [data-testid="stVerticalBlockBorderWrapper"] { 
        border-radius: 12px; padding: 20px; margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.08);
    }
    .stButton>button { 
        background-color: #007AFF !important; color: #FFFFFF !important; font-weight: bold; 
        border-radius: 8px; width: 100%; border: none; padding: 0.5rem 1rem; transition: all 0.2s;
    }
    .stButton>button:hover { background-color: #0056b3 !important; transform: scale(1.02); }
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; color: #007AFF !important; }
    .ranking-box {
        border-left: 5px solid #007AFF; border-radius: 8px; 
        padding: 15px 20px; margin-bottom: 12px; background-color: rgba(0, 122, 255, 0.05);
        border: 1px solid rgba(128,128,128,0.2);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群
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

def create_affiliate_link(url, aff_id):
    if not url: return "【URL未設定】"
    if not aff_id: return url
    if "hb.afl.rakuten.co.jp" in url: return url
    encoded_url = urllib.parse.quote(url, safe='')
    return f"https://hb.afl.rakuten.co.jp/hgc/{aff_id}/?pc={encoded_url}"

def save_to_sheets(sheet_id, g_json, row_data):
    if not sheet_id or not g_json: return False
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json, strict=False), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gspread.authorize(creds).open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except: return False

def get_sheet_data(sheet_id, g_json):
    if not sheet_id or not g_json: return []
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json, strict=False), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        data = gspread.authorize(creds).open_by_key(sheet_id).sheet1.get_all_values()
        if len(data) < 2: return []
        return [dict(zip(data[0], row)) for row in data[1:] if any(row)]
    except: return []

def get_templates(sheet_id, g_json):
    if not sheet_id or not g_json: return []
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json, strict=False), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        ws = gspread.authorize(creds).open_by_key(sheet_id).worksheet("テンプレート")
        data = ws.get_all_values()
        return [{"title": row[0], "content": row[1]} for row in data[1:] if len(row) >= 2 and row[0]]
    except: return []

def save_template(sheet_id, g_json, title, content):
    if not sheet_id or not g_json: return False
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json, strict=False), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        ss = gspread.authorize(creds).open_by_key(sheet_id)
        try: ws = ss.worksheet("テンプレート")
        except: 
            ws = ss.add_worksheet(title="テンプレート", rows=100, cols=2)
            ws.append_row(["タイトル", "本文"])
        ws.append_row([title, content])
        return True
    except: return False

def get_threads_engagement(token):
    if not token: return []
    try:
        threads = requests.get(f"https://graph.threads.net/v1.0/me/threads?fields=id,text,timestamp,is_reply&limit=100&access_token={token}").json().get("data", [])
        def fetch_insights(th):
            try:
                data = requests.get(f"https://graph.threads.net/v1.0/{th['id']}/insights?metric=views,likes,replies&access_token={token}").json().get("data", [])
                m = {d.get('name'): (d.get('values', [{}])[0].get('value', 0)) for d in data}
                th.update({'views': m.get('views',0), 'like_count': m.get('likes',0), 'reply_count': m.get('replies',0)})
            except: th.update({'views':0, 'like_count':0, 'reply_count':0})
            return th
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor: return list(executor.map(fetch_insights, threads))
    except: return []

def get_rakuten_ranking(app_id, access_key, affiliate_id, genre_id):
    if not app_id or not access_key: return []
    params = {"applicationId": str(app_id).strip(), "accessKey": str(access_key).strip(), "genreId": str(genre_id).strip()}
    if affiliate_id: params["affiliateId"] = str(affiliate_id).strip()
    try: return [item["Item"] for item in requests.get("https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601", params=params).json().get("Items", [])[:10]]
    except: return []

# 💡【重要改善】503混雑時対策＆複数モデル自動フォールバック
def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    if not api_key: return "❌ APIキーが未設定です"
    price_str = f"({price}円)" if price else ""
    prompt = f"""あなたは、SNSでリアルな本音を発信するインフルエンサーです。
以下の楽天商品「{item_name}」{price_str}を、ターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介してください。

【絶対厳守】
1. 宣伝感を消し、実体験に基づいた「本音・独り言」として書く。
2. 禁止語：〜をご存知ですか、結論から言うと、〜ですよね、チェックして、いかがでしたか。
3. 魅力を1点に絞り、読者が画像をタップしたくなる『余白』を残す。
"""
    if reference_post: prompt += f"\n【文体手本】\n{reference_post}\n"
    if custom_prompt: prompt += f"\n【特別指示】\n{custom_prompt}"
    
    client = genai.Client(api_key=api_key)
    models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(model=model_name, contents=[prompt, image] if image else prompt)
            return response.text
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                time.sleep(2)
                continue
            return f"❌ AIエラー: {e}"
    return "❌ サーバー混雑中。時間を置いてお試しください。"

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
# 🖥️ メイン構成
# ==========================================
local_storage = LocalStorage()

if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id": "", "rakuten_key": "", "rakuten_aff_id": "", "gemini": "", "threads": "", "sheet_id": "", "g_json": ""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. エンゲージメント分析", "4. API設定", "5. テンプレート管理"])

# --- 1. ダッシュボード ---
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    api = st.session_state["api_keys"]
    if not api["sheet_id"] or not api["threads"]: st.info("💡 API設定を行ってください。")
    else:
        st.subheader("📅 本日の投稿予定")
        sheet_data = get_sheet_data(api["sheet_id"], api["g_json"])
        today = datetime.now().strftime('%Y/%m/%d')
        today_pending = [r for r in sheet_data if r.get("投稿チェック", "") in ["pending", "予約中", ""] and r.get("投稿日", "") == today]
        if today_pending:
            preview = [{"予定時間": f"{p.get('時','')}:{p.get('分','')}", "本文": p.get('本文', '')[:40] + "..."} for p in today_pending]
            st.dataframe(preview, use_container_width=True, hide_index=True)
        else: st.success("本日の投稿予定はありません。")

        st.divider()
        st.subheader("📈 直近の状況")
        threads_data = get_threads_engagement(api["threads"])
        if threads_data:
            df = pd.DataFrame(threads_data)
            df['date_key'] = pd.to_datetime(df['timestamp']).dt.strftime('%m/%d')
            df_main = df[df['is_reply'] != True]
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("📝 投稿数", len(df_main)); st.bar_chart(df_main.groupby('date_key').size())
            with c2: st.metric("❤️ いいね", df_main['like_count'].sum()); st.bar_chart(df_main.groupby('date_key')['like_count'].sum(), color="#FF4B4B")
            with c3: st.metric("💬 返信", df_main['reply_count'].sum()); st.bar_chart(df_main.groupby('date_key')['reply_count'].sum(), color="#FFB800")

# --- 2. 商品作成＆予約 (全ジャンル・機能統合) ---
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    if not api["rakuten_id"] or not api["gemini"]: st.warning("API設定を完了してください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキングから", "🔗 URLから", "📸 画像から"])

        def draw_ui(k):
            c1, c2, c3 = st.columns(3)
            with c1: gen = st.radio("性別", ["女性", "男性", "指定なし"], key=f"gen_{k}")
            with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key=f"age_{k}")
            with c3: kids = st.radio("子供", ["なし", "あり"], key=f"kids_{k}")
            c4, c5 = st.columns(2)
            with c4: tone = st.selectbox("トーン", ["エモい", "役立つ", "元気", "親近感", "本音レビュー", "あざと可愛い", "高級感", "ズボラ命"], key=f"tone_{k}")
            with c5: length = st.slider("文字数", 10, 500, 50, step=10, key=f"len_{k}")
            sel_tmp = st.selectbox("🧠 テンプレート適用", ["手動入力"] + [t["title"] for t in templates], key=f"tmp_{k}")
            ref = next((t["content"] for t in templates if t["title"] == sel_tmp), "") if sel_tmp != "手動入力" else ""
            cp = st.text_area("✍️ 特別追加指示", key=f"cp_{k}")
            return f"{gen}, 年代:{','.join(age)}, 子供:{kids}", tone, length, ref, cp

        def show_final_ui(key, default_txt, default_url, default_img):
            with st.expander("✨ 投稿内容の確認・編集", expanded=True):
                use_img = st.checkbox("🖼️ 画像を添付する", value=True, key=f"uimg_{key}")
                dr_url = st.text_input("🔗 ドライブ画像URL (空なら初期画像)", value=default_img if default_img else "", key=f"dr_{key}")
                mk, rk = f"m_{key}", f"r_{key}"
                if mk not in st.session_state: st.session_state[mk] = default_txt
                if rk not in st.session_state: st.session_state[rk] = f"▼ 詳細はこちら\n{default_url}"
                st.text_area("本文", key=mk, height=150)
                st.text_area("リプライ (編集可)", key=rk, height=80)
                f_img = convert_drive_link(dr_url) if use_img and dr_url else (default_img if use_img else None)
                c1, c2 = st.columns(2)
                if c1.button("🚀 今すぐ投稿", key=f"now_{key}"):
                    mid = post_to_threads(api["threads"], st.session_state[mk], image_url=f_img)
                    if mid: time.sleep(5); post_to_threads(api["threads"], st.session_state[rk], reply_to_id=mid); st.success("投稿完了！")
                with c2:
                    dv, tv = st.date_input("予約日", key=f"dv_{key}"), st.time_input("時間", key=f"tv_{key}")
                    if st.button("🗓️ 予約に追加", key=f"res_{key}"):
                        row = ["", st.session_state[mk], dv.strftime('%Y/%m/%d'), str(tv.hour), str(tv.minute), "pending", "", "", st.session_state[rk], f_img if f_img else ""]
                        if save_to_sheets(api["sheet_id"], api["g_json"], row): st.success("予約保存完了")

        with tab1:
            # 💡 主要31ジャンル完全網羅！
            genres = {
                "🏆 総合ランキング": "0", "👗 レディース服": "100371", "👔 メンズ服": "551177", "👠 靴": "558885", 
                "👜 バッグ・ブランド": "216129", "⌚ 腕時計": "558929", "💄 美容・コスメ": "100939", 
                "💊 ダイエット・健康": "100143", "🏥 医薬品・介護": "551169", "🍎 食品": "100227", 
                "🍪 スイーツ": "551167", "🍹 水・ソフトドリンク": "100316", "🍺 ビール・洋酒": "510915", 
                "🍶 日本酒・焼酎": "510901", "🛋 インテリア・収納": "100804", "🍳 キッチン・食器": "558944", 
                "🚿 日用品雑貨": "215783", "🔌 家電": "562631", "📸 カメラ・スマホ": "211742", 
                "💻 パソコン": "100026", "⚽ スポーツ": "101070", "⛳ ゴルフ": "101077", 
                "🚗 車・バイク": "503190", "🧸 おもちゃ": "101164", "🎨 ホビー": "101165", 
                "🎮 ゲーム": "101205", "🎸 楽器": "112493", "📚 本・雑誌": "200376", 
                "📀 CD・DVD": "101240", "🍼 ベビー・キッズ": "100533", "🐱 ペット": "101213"
            }
            sel_g = st.selectbox("ジャンルを選択", list(genres.keys()), key="sg1")
            if st.button("ランキング取得", key="br1"):
                st.session_state["it1"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres[sel_g])
                if "res1" in st.session_state: del st.session_state["res1"]
            if "it1" in st.session_state:
                sel = []
                for i, item in enumerate(st.session_state["it1"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        if c2.checkbox(f"選ぶ: {item['itemName'][:50]}...", key=f"ch1_{i}"):
                            item["u_img"] = c2.file_uploader("📸 AI解析用スクショ", type=["jpg","png"], key=f"uf1_{i}"); sel.append(item)
                if sel:
                    st.divider(); t_str, tone, length, ref, cp = draw_ui("t1")
                    if st.button(f"✨ {len(sel)}件を一括生成", key="gen1"):
                        res_list = []
                        for s in sel:
                            img_obj = Image.open(s["u_img"]) if s["u_img"] else download_image(s["mediumImageUrls"][0]["imageUrl"])
                            txt = generate_post_text(s["itemName"], s["itemPrice"], t_str, tone, length, cp, ref, api["gemini"], img_obj)
                            res_list.append({"item": s, "text": txt})
                        st.session_state["res1"] = res_list
            if "res1" in st.session_state:
                for p in st.session_state["res1"]:
                    aff = create_affiliate_link(p["item"]["itemUrl"], str(api["rakuten_aff_id"]).strip())
                    show_final_ui(f"r1_{p['item']['itemCode']}", p["text"], aff, p["item"]["mediumImageUrls"][0]["imageUrl"])

        with tab2:
            url_in = st.text_input("楽天商品URL", key="u2")
            if st.button("情報取得", key="br2"):
                res = requests.get(url_in, headers={'User-Agent': 'Mozilla/5.0'}).text
                t_m = re.search(r'<title>(.*?)</title>', res, re.DOTALL)
                i_m = re.search(r'<meta\s+property="og:image"\s+content="(.*?)"', res)
                st.session_state["it2"] = {"name": t_m.group(1)[:50] if t_m else "商品", "img": i_m.group(1) if i_m else "", "url": url_in}
            if "it2" in st.session_state:
                it = st.session_state["it2"]; st.image(it["img"], width=150); t_str, tone, length, ref, cp = draw_ui("t2")
                if st.button("本文作成", key="gen2"):
                    st.session_state["res2"] = {"text": generate_post_text(it["name"], "", t_str, tone, length, cp, ref, api["gemini"], download_image(it["img"]))}
            if "res2" in st.session_state:
                show_final_ui("r2", st.session_state["res2"]["text"], create_affiliate_link(st.session_state["it2"]["url"], api["rakuten_aff_id"]), st.session_state["it2"]["img"])

        with tab3:
            st.info("🔗 画像URLを読み込ませて本文を作成し、投稿します。")
            img_url_t3 = st.text_input("🔗 画像URL (Googleドライブ等)", key="u3")
            hint_t3 = st.text_input("商品名ヒント", key="h3"); t_str, tone, length, ref, cp = draw_ui("t3")
            if st.button("本文作成", key="gen3"):
                txt = generate_post_text(hint_t3, "", t_str, tone, length, cp, ref, api["gemini"], download_image(img_url_t3))
                st.session_state["res3"] = {"text": txt, "url": img_url_t3}
            if "res3" in st.session_state:
                aff_url = st.text_input("🔗 アフィリエイトURL", key="aff3")
                show_final_ui("r3", st.session_state["res3"]["text"], create_affiliate_link(aff_url, api["rakuten_aff_id"]), st.session_state["res3"]["url"])

# --- 3. 分析 ---
elif page == "3. エンゲージメント分析":
    st.title("🔍 分析")
    api = st.session_state["api_keys"]
    if api["threads"]:
        threads_data = get_threads_engagement(api["threads"])
        if threads_data:
            df = pd.DataFrame(threads_data); df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            df = df[df['is_reply'] != True]
            st.subheader("📊 累計パフォーマンス")
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("👀 閲覧数", f"{df['views'].sum():,}")
            with c2: st.metric("❤️ いいね", f"{df['like_count'].sum():,}")
            with c3: st.metric("💬 コメント", f"{df['reply_count'].sum():,}")
            st.dataframe(df[['timestamp', 'text', 'views', 'like_count', 'reply_count']].sort_values(by='views', ascending=False), use_container_width=True, hide_index=True)

# --- 4. API設定 (ブラウザ保存対応) ---
elif page == "4. API設定":
    st.title("⚙️ API設定")
    stored_keys = local_storage.getItem("threads_keys")
    if stored_keys and "rakuten_id" in stored_keys and not st.session_state.get("f_ri"):
        for k, v in stored_keys.items(): st.session_state[f"f_{k}"] = v

    with st.expander("👤 管理者モード (Secretsロード)", expanded=True):
        pw = st.text_input("合言葉", type="password", key="apw")
        if st.button("一括ロード"):
            if pw == st.secrets.get("master_password"):
                st.session_state["f_ri"] = st.secrets.get("rakuten_id", ""); st.session_state["f_rk"] = st.secrets.get("rakuten_key", "")
                st.session_state["f_ra"] = st.secrets.get("rakuten_aff_id", ""); st.session_state["f_gk"] = st.secrets.get("gemini_key", "")
                st.session_state["f_tt"] = st.secrets.get("threads_token", ""); st.session_state["f_si"] = st.secrets.get("sheet_id", "")
                st.session_state["f_gj"] = st.secrets.get("g_json", ""); st.success("ロード完了！")
            else: st.error("❌ 合言葉が違います")

    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天 App ID", type="password", key="f_ri"); r_key = c1.text_input("楽天 Access Key", type="password", key="f_rk")
        r_aff = c1.text_input("楽天 アフィリエイトID", type="password", key="f_ra"); g_key = c2.text_input("Gemini API", type="password", key="f_gk")
        t_tok = c2.text_input("Threads Token", type="password", key="f_tt"); s_id = c2.text_input("Sheet ID", key="f_si")
        g_js = st.text_area("JSON", height=100, key="f_gj")
        if st.button("✅ 設定をブラウザに記憶して保存"):
            data = {"rakuten_id":r_id, "rakuten_key":r_key, "rakuten_aff_id":r_aff, "gemini_key":g_key, "threads_token":t_tok, "sheet_id":s_id, "g_json":g_js}
            st.session_state["api_keys"].update(data); local_storage.setItem("threads_keys", data); st.success("ブラウザに記憶しました！")

# --- 5. テンプレート管理 ---
elif page == "5. テンプレート管理":
    st.title("📝 テンプレート管理")
    api = st.session_state["api_keys"]
    if not api["sheet_id"]: st.warning("API設定を完了してください。")
    else:
        with st.form("tf"):
            t_title = st.text_input("テンプレート名"); t_content = st.text_area("バズ投稿本文", height=150)
            if st.form_submit_button("保存"):
                if save_template(api["sheet_id"], api["g_json"], t_title, t_content):
                    st.success("保存完了！"); time.sleep(1); st.rerun()
        st.divider(); templates = get_templates(api["sheet_id"], api["g_json"])
        for t in templates:
            with st.expander(t["title"]): st.write(t["content"])
