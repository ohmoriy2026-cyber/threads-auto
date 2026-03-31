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
# 🎨 UIデザイン設定
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    [data-testid="stHeaderActionElements"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    .stAppDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    header { visibility: visible !important; background: transparent !important; }
    .stApp { font-family: 'Helvetica Neue', Arial, sans-serif; }
    [data-testid="stVerticalBlockBorderWrapper"] { 
        border-radius: 12px; padding: 20px; margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: transform 0.2s ease;
    }
    .stButton>button { 
        background-color: #007AFF !important; color: #FFFFFF !important; font-weight: bold; 
        border-radius: 8px; width: 100%; border: none; padding: 0.5rem 1rem;
    }
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; color: #007AFF !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群
# ==========================================

local_storage = LocalStorage()

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
        res = requests.get(convert_drive_link(url), timeout=10)
        return Image.open(io.BytesIO(res.content))
    except: return None

def create_affiliate_link(url, aff_id):
    if not url: return "【URL未設定】"
    if not aff_id: return url
    if "hb.afl.rakuten.co.jp" in url: return url
    return f"https://hb.afl.rakuten.co.jp/hgc/{aff_id}/?pc={urllib.parse.quote(url, safe='')}"

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
        except: ws = ss.add_worksheet(title="テンプレート", rows=100, cols=2); ws.append_row(["タイトル", "本文"])
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

def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    if not api_key: return "❌ APIキーが未設定です"
    price_str = f"({price}円)" if price else ""
    prompt = f"""あなたは、SNSでリアルな本音を発信するインフルエンサーです。商品「{item_name}」{price_str}を、ターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介してください。
【絶対厳守】1. 宣伝感を消し、実体験の本音として書く。2. 禁止語：ご存知ですか、結論から、ですよね、いかがでしたか。3. 魅力を1点に絞り、読者が画像をタップしたくなる『余白』を残す。"""
    if reference_post: prompt += f"\n【文体手本】\n{reference_post}\n"
    if custom_prompt: prompt += f"\n【特別指示】\n{custom_prompt}"
    
    client = genai.Client(api_key=api_key)
    for model_name in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']:
        try:
            return client.models.generate_content(model=model_name, contents=[prompt, image] if image else prompt).text
        except: time.sleep(2); continue
    return "❌ サーバー混雑中。"

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
# 🖥️ 初期化 ＆ データ同期
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id": "", "rakuten_key": "", "rakuten_aff_id": "", "gemini": "", "threads": "", "sheet_id": "", "g_json": ""}

stored = local_storage.getItem("threads_marketing_keys")
if stored and not st.session_state["api_keys"]["rakuten_id"]:
    st.session_state["api_keys"].update({
        "rakuten_id": stored.get("rakuten_id", ""), "rakuten_key": stored.get("rakuten_key", ""), "rakuten_aff_id": stored.get("rakuten_aff_id", ""),
        "gemini": stored.get("gemini_key", ""), "threads": stored.get("threads_token", ""), "sheet_id": stored.get("sheet_id", ""), "g_json": stored.get("g_json", "")
    })

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. エンゲージメント分析", "4. API設定", "5. テンプレート管理"])
api = st.session_state["api_keys"]

# --- 1. ダッシュボード ---
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    if not api["rakuten_id"] or not api["threads"]: st.warning("⚠️ API設定を行ってください。")
    else:
        sheet_data = get_sheet_data(api["sheet_id"], api["g_json"])
        today = datetime.now().strftime('%Y/%m/%d')
        today_pending = [r for r in sheet_data if r.get("投稿チェック", "") in ["pending", "予約中", ""] and r.get("投稿日", "") == today]
        if today_pending: st.dataframe([{"時間": f"{p.get('時','')}:{p.get('分','')}", "本文": p.get('本文', '')[:40]} for p in today_pending], use_container_width=True, hide_index=True)
        else: st.success("本日の予定はありません。")
        st.divider()
        threads_data = get_threads_engagement(api["threads"])
        if threads_data:
            df = pd.DataFrame(threads_data); df['date'] = pd.to_datetime(df['timestamp']).dt.strftime('%m/%d'); df_m = df[df['is_reply'] != True]
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("📝 投稿", len(df_m)); st.bar_chart(df_m.groupby('date').size())
            with c2: st.metric("❤️ いいね", df_m['like_count'].sum()); st.bar_chart(df_m.groupby('date')['like_count'].sum(), color="#FF4B4B")
            with c3: st.metric("💬 返信", df_m['reply_count'].sum()); st.bar_chart(df_m.groupby('date')['reply_count'].sum(), color="#FFB800")

# --- 2. 商品作成＆予約 ---
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    if not api["rakuten_id"] or not api["gemini"]: st.warning("⚠️ API設定を行ってください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキング", "🔗 URL", "📸 画像"])
        def draw_ui(k):
            c1, c2, c3 = st.columns(3)
            with c1: gen = st.radio("性別", ["女性", "男性", "指定なし"], key=f"gen_{k}")
            with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key=f"age_{k}")
            with c3: kids = st.radio("子供", ["なし", "乳児", "幼児", "小学生"], key=f"kids_{k}")
            c4, c5 = st.columns(2)
            with c4: tone = st.selectbox("トーン", ["エモい", "役立つ", "元気", "親近感", "本音レビュー", "あざと可愛い", "高級感", "ズボラ命"], key=f"tone_{k}")
            with c5: length = st.slider("文字数", 10, 500, 50, step=10, key=f"len_{k}")
            sel_tmp = st.selectbox("🧠 テンプレート適用", ["手動入力"] + [t["title"] for t in templates], key=f"tmp_{k}")
            ref = next((t["content"] for t in templates if t["title"] == sel_tmp), "") if sel_tmp != "手動入力" else ""
            cp = st.text_area("✍️ 特別指示", key=f"cp_{k}")
            return f"{gen}, {','.join(age)}, 子供:{kids}", tone, length, ref, cp

        def show_final_ui(key, def_txt, def_url, def_img):
            with st.expander("✨ 投稿内容の確認・編集", expanded=True):
                ui = st.checkbox("🖼️ 画像あり", value=True, key=f"ui_{key}")
                dr = st.text_input("🔗 ドライブ画像URL", value=def_img if def_img else "", key=f"dr_{key}")
                m_k, r_k = f"mt_{key}", f"rt_{key}"
                if m_k not in st.session_state: st.session_state[m_k] = def_txt
                if r_k not in st.session_state: st.session_state[r_k] = f"▼ 詳細はこちら\n{def_url}"
                st.text_area("本文", key=m_k, height=150); st.text_area("リプライ", key=r_k, height=80)
                f_img = convert_drive_link(dr) if ui and dr else (def_img if ui else None)
                c1, c2 = st.columns(2)
                if c1.button("🚀 今すぐ投稿", key=f"now_{key}"):
                    mid = post_to_threads(api["threads"], st.session_state[m_k], image_url=f_img)
                    if mid: time.sleep(5); post_to_threads(api["threads"], st.session_state[r_k], reply_to_id=mid); st.success("完了！")
                with c2:
                    dv, tv = st.date_input("予約日", key=f"dv_{key}"), st.time_input("時間", key=f"tv_{key}")
                    if st.button("🗓️ 予約に追加", key=f"res_{key}"):
                        row = ["", st.session_state[m_k], dv.strftime('%Y/%m/%d'), str(tv.hour), str(tv.minute), "pending", "", "", st.session_state[r_k], f_img if f_img else ""]
                        if save_to_sheets(api["sheet_id"], api["g_json"], row): st.success("保存完了")

        with tab1:
            genres = {"🏆 総合": "0", "👗 レディース": "100371", "👔 メンズ": "551177", "👠 靴": "558885", "👜 バッグ": "216129", "⌚ 腕時計": "558929", "💄 美容": "100939", "💊 健康": "100143", "🏥 介護": "551169", "🍎 食品": "100227", "🍪 スイーツ": "551167", "🍹 飲料": "100316", "🍺 洋酒": "510915", "🍶 日本酒": "510901", "🛋 インテリア": "100804", "🍳 キッチン": "558944", "🚿 日用品": "215783", "🔌 家電": "562631", "📸 カメラ": "211742", "💻 パソコン": "100026", "📱 スマホ": "562637", "⚽ スポーツ": "101070", "⛳ ゴルフ": "101077", "🚗 車": "503190", "🧸 おもちゃ": "101164", "🎨 ホビー": "101165", "🎮 ゲーム": "101205", "🎸 楽器": "112493", "📚 本": "200376", "📀 CD・DVD": "101240", "🍼 ベビー": "100533", "🐱 ペット": "101213"}
            sel_g = st.selectbox("ジャンル", list(genres.keys()), key="sg_tab1")
            if st.button("ランキング取得", key="br_tab1"):
                st.session_state["it1"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres[sel_g])
            if "it1" in st.session_state:
                sel = []
                for i, item in enumerate(st.session_state["it1"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        if c2.checkbox(f"選ぶ: {item['itemName'][:50]}", key=f"ch1_{i}"):
                            item["u_img"] = c2.file_uploader("📸 スクショ添付", type=["jpg","png"], key=f"uf1_{i}"); sel.append(item)
                if sel:
                    t_str, tone, length, ref, cp = draw_ui("t1")
                    if st.button(f"✨ {len(sel)}件を一括生成", key="gen_tab1"):
                        st.session_state["res1"] = [{"item": s, "text": generate_post_text(s["itemName"], s["itemPrice"], t_str, tone, length, cp, ref, api["gemini"], Image.open(s["u_img"]) if s["u_img"] else download_image(s["mediumImageUrls"][0]["imageUrl"]))} for s in sel]
            if "res1" in st.session_state:
                for p in st.session_state["res1"]: show_final_ui(f"r1_{p['item']['itemCode']}", p["text"], create_affiliate_link(p["item"]["itemUrl"], api["rakuten_aff_id"]), p["item"]["mediumImageUrls"][0]["imageUrl"])

        with tab2:
            url_in = st.text_input("楽天商品URL", key="u_tab2")
            if st.button("情報取得", key="br_tab2"):
                res = requests.get(url_in, headers={'User-Agent': 'Mozilla/5.0'}).text
                t_m = re.search(r'<title>(.*?)</title>', res, re.DOTALL); i_m = re.search(r'<meta\s+property="og:image"\s+content="(.*?)"', res)
                st.session_state["it2"] = {"name": t_m.group(1)[:50] if t_m else "商品", "img": i_m.group(1) if i_m else "", "url": url_in}
            if "it2" in st.session_state:
                it = st.session_state["it2"]; st.image(it["img"], width=150); t_str, tone, length, ref, cp = draw_ui("t2")
                if st.button("✨ 本文作成", key="gen_tab2"):
                    st.session_state["res2"] = {"text": generate_post_text(it["name"], "", t_str, tone, length, cp, ref, api["gemini"], download_image(it["img"]))}
            if "res2" in st.session_state: show_final_ui("r2", st.session_state["res2"]["text"], create_affiliate_link(st.session_state["it2"]["url"], api["rakuten_aff_id"]), st.session_state["it2"]["img"])

        with tab3:
            img_url_t3 = st.text_input("🔗 画像URL", key="u_tab3")
            hint_t3 = st.text_input("商品名ヒント", key="h_tab3"); t_str, tone, length, ref, cp = draw_ui("t3")
            if st.button("✨ 本文を作成", key="gen_tab3"):
                if img_url_t3 or hint_t3:
                    txt = generate_post_text(hint_t3, "", t_str, tone, length, cp, ref, api["gemini"], download_image(img_url_t3))
                    st.session_state["res3"] = {"text": txt, "url": img_url_t3}
                else: st.error("画像URLかヒントを入力してください。")
            if "res3" in st.session_state:
                uf_t3 = st.file_uploader("📸 【追加】スクショ添付", type=["jpg","png"], key="uf_tab3")
                aff_t3 = st.text_input("🔗 アフィ商品URL", key="aff_tab3")
                show_final_ui("res3_f", st.session_state["res3"]["text"], create_affiliate_link(aff_t3, api["rakuten_aff_id"]), st.session_state["res3"]["url"])

# --- 3. 分析 ---
elif page == "3. エンゲージメント分析":
    st.title("🔍 分析")
    if not api["threads"]: st.warning("⚠️ API設定を行ってください。")
    else:
        threads_data = get_threads_engagement(api["threads"])
        if threads_data:
            df = pd.DataFrame(threads_data); df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date; df = df[df['is_reply'] != True]
            st.subheader("📊 パフォーマンス")
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("👀 閲覧", f"{df['views'].sum():,}")
            with c2: st.metric("❤️ いいね", f"{df['like_count'].sum():,}")
            with c3: st.metric("💬 コメント", f"{df['reply_count'].sum():,}")
            st.dataframe(df[['timestamp', 'text', 'views', 'like_count', 'reply_count']].sort_values(by='views', ascending=False), use_container_width=True, hide_index=True)

# --- 4. API設定 ---
elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード", expanded=True):
        pw = st.text_input("合言葉", type="password", key="m_pw_in")
        if st.button("一括ロード", key="b_secrets_load"):
            if pw == st.secrets.get("master_password"):
                st.session_state["api_keys"].update({"rakuten_id":st.secrets.get("rakuten_id",""),"rakuten_key":st.secrets.get("rakuten_key",""),"rakuten_aff_id":st.secrets.get("rakuten_aff_id",""),"gemini":st.secrets.get("gemini_key",""),"threads":st.secrets.get("threads_token",""),"sheet_id":st.secrets.get("sheet_id",""),"g_json":st.secrets.get("g_json","")})
                st.success("✅ ロードしました！"); st.rerun()
            else: st.error("❌ 違います")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天 App ID", value=api["rakuten_id"], type="password", key="r_id_set")
        r_key = c1.text_input("楽天 Access Key", value=api["rakuten_key"], type="password", key="r_key_set")
        r_aff = c1.text_input("楽天 Aff ID", value=api["rakuten_aff_id"], type="password", key="r_aff_set")
        g_key = c2.text_input("Gemini API", value=api["gemini"], type="password", key="g_key_set")
        t_tok = c2.text_input("Threads Token", value=api["threads"], type="password", key="t_tok_set")
        s_id = c2.text_input("Sheet ID", value=api["sheet_id"], key="s_id_set")
        g_js = st.text_area("GCloud JSON", value=api["g_json"], height=100, key="g_js_set")
        if st.button("✅ 設定を保存", key="b_save_set"):
            d = {"rakuten_id":r_id,"rakuten_key":r_key,"rakuten_aff_id":r_aff,"gemini":g_key,"threads":t_tok,"sheet_id":s_id,"g_json":g_js}
            st.session_state["api_keys"].update(d); local_storage.setItem("threads_marketing_keys", d); st.success("🎉 保存完了！"); st.rerun()

# --- 5. テンプレート管理 ---
elif page == "5. テンプレート管理":
    st.title("📝 テンプレート管理")
    if not api["sheet_id"]: st.warning("⚠️ API設定を行ってください。")
    else:
        with st.form("tf_form"):
            t_ti = st.text_input("テンプレート名"); t_co = st.text_area("本文", height=150)
            if st.form_submit_button("保存", key="b_tmp_save"):
                if save_template(api["sheet_id"], api["g_json"], t_ti, t_co): st.success("保存完了！"); time.sleep(1); st.rerun()
        st.divider(); templates = get_templates(api["sheet_id"], api["g_json"])
        for t in templates:
            with st.expander(t["title"]): st.write(t["content"])
