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
import hashlib
import base64
from cryptography.fernet import Fernet

# ==========================================
# 🎨 ページ設定
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="collapsed")

if "current_page" not in st.session_state:
    st.session_state["current_page"] = "1. ダッシュボード"

page = st.session_state["current_page"]

# ==========================================
# 🧭 ナビゲーションバー
# ==========================================
st.markdown("""
<style>
    .stApp {
        font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px; padding: 20px; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; color: #007AFF !important; }
    .stAppDeployButton,
    [data-testid="stHeaderActionElements"],
    [data-testid="stViewerBadge"],
    [data-testid="stDecoration"],
    [data-testid="stToolbar"],
    [data-testid="stToolbarActions"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebar"],
    a[href*="github.com"],
    .stActionButton,
    #MainMenu, header, footer {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important; height: 0 !important;
        overflow: hidden !important;
    }
    [data-testid="stHorizontalBlock"].nav-bar {
        position: fixed !important;
        top: 0 !important; left: 0 !important; right: 0 !important;
        z-index: 9999999 !important;
        background: #ffffff !important;
        border-bottom: 2px solid #007AFF !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08) !important;
        padding: 4px 8px !important;
    }
    div[data-testid="stHorizontalBlock"] > div > div > div > button {
        background: transparent !important;
        color: #444 !important;
        border: none !important;
        border-bottom: 3px solid transparent !important;
        border-radius: 0 !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        padding: 8px 6px !important;
        width: 100% !important;
        box-shadow: none !important;
        transition: all 0.2s !important;
        white-space: nowrap !important;
    }
    div[data-testid="stHorizontalBlock"] > div > div > div > button:hover {
        color: #007AFF !important;
        border-bottom-color: #007AFF !important;
        background: rgba(0,122,255,0.05) !important;
    }
    .main .block-container {
        padding-top: 70px !important;
        max-width: 100% !important;
    }
</style>
""", unsafe_allow_html=True)

nav_pages = [
    ("📊 ダッシュボード", "1. ダッシュボード"),
    ("🛍 商品作成", "2. 商品作成＆予約"),
    ("📈 分析", "3. エンゲージメント分析"),
    ("⚙️ API設定", "4. API設定"),
    ("📝 テンプレート", "5. テンプレート管理"),
]

cols = st.columns(len(nav_pages))
for col, (label, page_name) in zip(cols, nav_pages):
    btn_label = f"**{label}**" if page == page_name else label
    if col.button(btn_label, key=f"nav_{page_name}", use_container_width=True):
        st.session_state["current_page"] = page_name
        st.rerun()

st.divider()

# ==========================================
# 🔐 暗号化ユーティリティ
# ==========================================

def _get_fernet():
    raw_key = st.secrets.get("ENCRYPT_KEY", "default-key-please-change")
    hashed = hashlib.sha256(raw_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(hashed))

def encrypt_data(data: dict) -> str:
    return _get_fernet().encrypt(json.dumps(data).encode()).decode()

def decrypt_data(token: str) -> dict:
    return json.loads(_get_fernet().decrypt(token.encode()).decode())

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 📋 管理用スプレッドシート操作
# ==========================================

def _get_admin_sheet():
    admin_sheet_id = st.secrets.get("ADMIN_SHEET_ID", "")
    admin_g_json   = st.secrets.get("ADMIN_G_JSON", "").strip()  # ヒアドキュメント対応
    if not admin_sheet_id or not admin_g_json:
        return None
    try:
        creds = Credentials.from_service_account_info(
            json.loads(admin_g_json, strict=False),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        ss = client.open_by_key(admin_sheet_id)
        try:
            ws = ss.worksheet("users")
        except:
            ws = ss.add_worksheet(title="users", rows=500, cols=4)
            ws.append_row(["user_name", "password_hash", "api_keys_encrypted", "registered_at"])
        return ws
    except Exception as e:
        st.error(f"管理シート接続エラー: {e}")
        return None

def register_user(user_name: str, password: str, api_keys: dict) -> bool:
    try:
        ws = _get_admin_sheet()
        if ws is None:
            st.error("管理用スプレッドシートの設定が不足しています。")
            return False
        all_rows = ws.get_all_values()
        pw_hash = hash_password(password)
        for row in all_rows[1:]:
            if len(row) >= 2 and row[1] == pw_hash:
                st.error("❌ その合言葉は既に使われています。別の合言葉を設定してください。")
                return False
        ws.append_row([user_name, pw_hash, encrypt_data(api_keys), datetime.now().strftime("%Y/%m/%d %H:%M")])
        return True
    except Exception as e:
        st.error(f"登録エラー: {e}")
        return False

def login_user(password: str):
    try:
        ws = _get_admin_sheet()
        if ws is None:
            return None, None
        pw_hash = hash_password(password)
        for row in ws.get_all_values()[1:]:
            if len(row) >= 3 and row[1] == pw_hash:
                return decrypt_data(row[2]), row[0]
    except Exception as e:
        st.error(f"ログインエラー: {e}")
    return None, None

def update_user_api(password: str, api_keys: dict) -> bool:
    try:
        ws = _get_admin_sheet()
        if ws is None:
            return False
        pw_hash = hash_password(password)
        for i, row in enumerate(ws.get_all_values()[1:], start=2):
            if len(row) >= 3 and row[1] == pw_hash:
                ws.update_cell(i, 3, encrypt_data(api_keys))
                ws.update_cell(i, 4, datetime.now().strftime("%Y/%m/%d %H:%M"))
                return True
    except Exception as e:
        st.error(f"更新エラー: {e}")
    return False

# ==========================================
# ⚙️ アプリ関数群
# ==========================================

def _parse_json(s):
    """前後の空白・改行を除去してjson.loadsする（ヒアドキュメント対応）"""
    return json.loads(s.strip(), strict=False)

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

def clean_image_url(url):
    """楽天サムネイルのサイズ指定パラメータを除去して高画質URLに変換"""
    if not url: return url
    url = re.sub(r'[?&]_ex=\d+x\d+', '', url)
    return url

def shorten_url(url):
    if not url or "http" not in url: return url
    try:
        safe_url = urllib.parse.quote(url, safe="")
        res = requests.get(f"https://tinyurl.com/api-create.php?url={safe_url}", timeout=10)
        if res.status_code == 200 and "tinyurl.com" in res.text:
            return res.text.strip()
    except: pass
    try:
        res = requests.get(f"https://is.gd/create.php?format=simple&url={urllib.parse.quote(url, safe='')}", timeout=10)
        if res.status_code == 200 and "is.gd" in res.text:
            return res.text.strip()
    except: pass
    return url

def create_affiliate_link(url, aff_id):
    if not url: return "【URL未設定】"
    if not aff_id: return url
    if "hb.afl.rakuten.co.jp" not in url:
        encoded_url = urllib.parse.quote(url, safe='')
        long_aff_url = f"https://hb.afl.rakuten.co.jp/hgc/{aff_id}/?pc={encoded_url}"
    else:
        long_aff_url = url
    return shorten_url(long_aff_url)

def save_to_sheets(sheet_id, g_json, row_data):
    if not sheet_id or not g_json: return False
    try:
        creds = Credentials.from_service_account_info(
            _parse_json(g_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).worksheet("sheet")
        all_values = sheet.get_all_values()
        next_row = 1
        for i, row in enumerate(all_values):
            if any(str(val).strip() for val in row):
                next_row = i + 2
        if next_row > sheet.row_count:
            sheet.add_rows(next_row - sheet.row_count)
        cells = sheet.range(f"A{next_row}:J{next_row}")
        for i, val in enumerate(row_data):
            cells[i].value = str(val) if val is not None else ""
        sheet.update_cells(cells)
        return True
    except Exception as e:
        st.error(f"スプレッドシート保存エラー: {e}")
        return False

def get_sheet_data(sheet_id, g_json):
    try:
        creds = Credentials.from_service_account_info(
            _parse_json(g_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        data = gspread.authorize(creds).open_by_key(sheet_id).worksheet("sheet").get_all_values()
        if len(data) < 2: return []
        return [dict(zip(data[0], row)) for row in data[1:] if any(row)]
    except: return []

def get_templates(sheet_id, g_json):
    try:
        creds = Credentials.from_service_account_info(
            _parse_json(g_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        data = gspread.authorize(creds).open_by_key(sheet_id).worksheet("テンプレート").get_all_values()
        return [{"title": row[0], "content": row[1]} for row in data[1:] if len(row) >= 2 and row[0]]
    except: return []

def save_template(sheet_id, g_json, title, content):
    try:
        creds = Credentials.from_service_account_info(
            _parse_json(g_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        ss = gspread.authorize(creds).open_by_key(sheet_id)
        try: ws = ss.worksheet("テンプレート")
        except:
            ws = ss.add_worksheet(title="テンプレート", rows=100, cols=2)
            ws.append_row(["タイトル", "本文"])
        all_values = ws.get_all_values()
        next_row = 1
        for i, row in enumerate(all_values):
            if any(str(val).strip() for val in row):
                next_row = i + 2
        if next_row > ws.row_count:
            ws.add_rows(next_row - ws.row_count)
        cells = ws.range(f"A{next_row}:B{next_row}")
        cells[0].value = str(title)
        cells[1].value = str(content)
        ws.update_cells(cells)
        return True
    except: return False

def get_threads_user_name(token):
    try: return requests.get(f"https://graph.threads.net/v1.0/me?fields=username&access_token={token}").json().get("username")
    except: return None

def get_threads_engagement(token):
    try:
        threads = requests.get(
            f"https://graph.threads.net/v1.0/me/threads?fields=id,text,timestamp,is_reply&limit=100&access_token={token}"
        ).json().get("data", [])
        def fetch_insights(th):
            try:
                m = {d['name']: d['values'][0]['value'] for d in requests.get(
                    f"https://graph.threads.net/v1.0/{th['id']}/insights?metric=views,likes,replies&access_token={token}"
                ).json().get("data", [])}
                th.update({'views': m.get('views',0), 'like_count': m.get('likes',0), 'reply_count': m.get('replies',0)})
            except: th.update({'views':0,'like_count':0,'reply_count':0})
            return th
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            return list(executor.map(fetch_insights, threads))
    except: return []

def get_rakuten_ranking(app_id, access_key, affiliate_id, genre_id):
    try:
        return [item["Item"] for item in requests.get(
            "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601",
            params={"applicationId":app_id,"accessKey":access_key,"genreId":genre_id,"affiliateId":affiliate_id}
        ).json().get("Items", [])[:10]]
    except: return []

def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    if not api_key: return "❌ APIキー未設定"
    prompt = f"インフルエンサーとして商品「{item_name}」({price}円)をターゲット【{target_str}】へ{tone}テイストで約{length}文字で紹介。本音レビュー風、宣伝感禁止。"
    if reference_post: prompt += f"\n手本:{reference_post}"
    if custom_prompt: prompt += f"\n指示:{custom_prompt}"
    client = genai.Client(api_key=api_key)
    for model_name in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']:
        try: return client.models.generate_content(model=model_name, contents=[prompt, image] if image else prompt).text
        except: time.sleep(2); continue
    return "❌ サーバー混雑中"

def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    try:
        # 必須パラメータのみ先にセット
        params = {
            "access_token": access_token,
            "text": text,
            "media_type": "IMAGE" if image_url else "TEXT",
        }
        # 値がある場合のみ追加（空文字をAPIに送るとエラーになるため）
        if image_url:
            params["image_url"] = image_url
        if reply_to_id:
            params["reply_to_id"] = reply_to_id

        res = requests.post("https://graph.threads.net/v1.0/me/threads", params=params)
        if res.status_code == 200:
            cid = res.json().get("id")
            time.sleep(5)
            requests.post(
                "https://graph.threads.net/v1.0/me/threads_publish",
                params={"access_token": access_token, "creation_id": cid}
            )
            return cid
    except: pass
    return None

# ==========================================
# 🖥️ 初期化
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {
        "rakuten_id": "", "rakuten_key": "", "rakuten_aff_id": "",
        "gemini": "", "threads": "", "sheet_id": "", "g_json": ""
    }
if "gen_count" not in st.session_state:
    st.session_state["gen_count"] = 0
if "loaded_user" not in st.session_state:
    st.session_state["loaded_user"] = ""

api = st.session_state["api_keys"]

# ==========================================
# --- 1. ダッシュボード ---
# ==========================================
if page == "1. ダッシュボード":
    u_name = get_threads_user_name(api["threads"])
    st.title(f"📊 {u_name if u_name else ''} のダッシュボード")
    if not api["rakuten_id"] or not api["threads"]:
        st.warning("⚠️ API設定を行ってください。")
    else:
        sheet_data = get_sheet_data(api["sheet_id"], api["g_json"])
        today = datetime.now().strftime('%Y/%m/%d')
        today_pending = [r for r in sheet_data if r.get("投稿チェック", "") in ["pending", "予約中", ""] and r.get("投稿日", "") == today]
        if today_pending:
            st.dataframe(
                [{"時間": f"{p.get('時','')}:{p.get('分','')}", "本文": p.get('本文', '')[:40]} for p in today_pending],
                use_container_width=True, hide_index=True
            )
        else:
            st.success("本日の予定はありません。")
        st.divider()
        threads_data = get_threads_engagement(api["threads"])
        if threads_data:
            df = pd.DataFrame(threads_data)
            df['date'] = pd.to_datetime(df['timestamp']).dt.strftime('%m/%d')
            df_m = df[df['is_reply'] != True]
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("📝 投稿", len(df_m)); st.bar_chart(df_m.groupby('date').size())
            with c2: st.metric("❤️ いいね", df_m['like_count'].sum()); st.bar_chart(df_m.groupby('date')['like_count'].sum(), color="#FF4B4B")
            with c3: st.metric("💬 返信", df_m['reply_count'].sum()); st.bar_chart(df_m.groupby('date')['reply_count'].sum(), color="#FFB800")

# ==========================================
# --- 2. 商品作成＆予約 ---
# ==========================================
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    if not api["rakuten_id"] or not api["gemini"]:
        st.warning("⚠️ API設定を行ってください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキング", "🔗 URL", "📸 画像"])

        def show_final_ui(key, def_txt, def_url, def_img):
            uid = f"{key}_{st.session_state['gen_count']}"
            with st.expander("✨ 投稿確認", expanded=True):
                ui = st.checkbox("🖼️ 画像あり", value=True, key=f"ui_{uid}")
                dr = st.text_input("🔗 Googleドライブの画像URLを入力", value=def_img if def_img else "", key=f"dr_{uid}")
                m_txt = st.text_area("本文", value=def_txt, height=150, key=f"mt_{uid}")
                r_txt = st.text_area("リプライ", value=f"▼ 詳細はこちら\n{def_url}", height=80, key=f"rt_{uid}")
                f_img = convert_drive_link(dr) if ui and dr else (def_img if ui else None)
                c1, c2 = st.columns(2)
                if c1.button("🚀 今すぐ投稿", key=f"now_{uid}"):
                    with st.spinner("投稿中..."):
                        mid = post_to_threads(api["threads"], m_txt, image_url=f_img)
                        if mid:
                            time.sleep(2)
                            post_to_threads(api["threads"], r_txt, reply_to_id=mid)
                            st.success("🎉 投稿完了しました！"); st.balloons()
                with c2:
                    dv = st.date_input("予約日", key=f"dv_{uid}")
                    tv = st.time_input("時間", key=f"tv_{uid}")
                    if st.button("🗓️ 予約に追加", key=f"res_{uid}"):
                        with st.spinner("保存中..."):
                            row = [
                                "",                        # A: NO
                                m_txt,                     # B: 本文
                                dv.strftime('%Y/%m/%d'),   # C: 投稿日
                                str(tv.hour),              # D: 時
                                str(tv.minute),            # E: 分
                                "",                        # F: 投稿チェック
                                "",                        # G: 投稿URL
                                dr,                        # H: Googleドライブ画像URL
                                r_txt,                     # I: 返信コメント内容
                                f_img if f_img else ""     # J: 画像URL
                            ]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                st.success("✅ 予約保存完了！")

        with tab1:
            genres = {
                "🏆 総合": "0", "👗 レディース": "100371", "👔 メンズ": "551177",
                "👠 靴": "558885", "👜 バッグ": "216129", "⌚ 腕時計": "558929",
                "💄 美容": "100939", "💊 健康": "100143", "🏥 介護": "551169",
                "🍎 食品": "100227", "🍪 スイーツ": "551167", "🍹 飲料": "100316",
                "🍺 洋酒": "510915", "🍶 日本酒": "510901", "🛋 インテリア": "100804",
                "🍳 キッチン": "558944", "🚿 日用品": "215783", "🔌 家電": "562631",
                "📸 カメラ": "211742", "💻 パソコン": "100026", "📱 スマホ": "562637",
                "⚽ スポーツ": "101070", "⛳ ゴルフ": "101077", "🚗 車": "503190",
                "🧸 おもちゃ": "101164", "🎨 ホビー": "101165", "🎮 ゲーム": "101205",
                "🎸 楽器": "112493", "📚 本": "200376", "📀 CD・DVD": "101240",
                "🍼 ベビー": "100533", "🐱 ペット": "101213"
            }
            sel_g = st.selectbox("ジャンルを選択", list(genres.keys()), key="sg_t1")
            if st.button("ランキング取得", key="br_t1"):
                if "res1" in st.session_state: del st.session_state["res1"]
                st.session_state["it1"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres[sel_g])
            if "it1" in st.session_state:
                sel = []
                for i, item in enumerate(st.session_state["it1"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        if c2.checkbox(f"選ぶ: {item['itemName'][:50]}", key=f"ch1_{i}"):
                            uf = c2.file_uploader("📸 解析用", type=["jpg","png"], key=f"uf1_{i}")
                            item["u_img_file"] = uf; sel.append(item)
                if sel:
                    st.divider()
                    c1, c2, c3 = st.columns(3)
                    with c1: gen = st.radio("性別", ["女性", "男性", "指定なし"], key="gen_t1")
                    with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="age_t1")
                    with c3: kids = st.radio("子供", ["なし", "乳児", "幼児", "小学生"], key="kids_t1")
                    c4, c5 = st.columns(2)
                    with c4: tone = st.selectbox("トーン", ["エモい", "役立つ", "元気", "親近感", "本音レビュー", "あざと可愛い", "高級感", "ズボラ命"], key="tone_t1")
                    with c5: length = st.slider("文字数", 10, 500, 50, step=10, key="len_t1")
                    sel_tmp = st.selectbox("🧠 テンプレート適用", ["手動入力"] + [t["title"] for t in templates], key="tmp_t1")
                    ref = next((t["content"] for t in templates if t["title"] == sel_tmp), "") if sel_tmp != "手動入力" else ""
                    cp = st.text_area("✍️ 特別指示", key="cp_t1")
                    if st.button(f"✨ {len(sel)}件を一括生成", key="gen_btn_t1"):
                        with st.spinner("AI文章作成中..."):
                            st.session_state["gen_count"] += 1
                            st.session_state["res1"] = [
                                {"item": s, "text": generate_post_text(
                                    s["itemName"], s["itemPrice"],
                                    f"{gen}, {','.join(age)}, 子供:{kids}",
                                    tone, length, cp, ref, api["gemini"],
                                    Image.open(s["u_img_file"]) if s.get("u_img_file") else download_image(s["mediumImageUrls"][0]["imageUrl"])
                                )} for s in sel
                            ]
                            st.rerun()
            if "res1" in st.session_state:
                for p in st.session_state["res1"]:
                    show_final_ui(
                        f"r1_{p['item']['itemCode']}", p["text"],
                        create_affiliate_link(p["item"]["itemUrl"], api["rakuten_aff_id"]),
                        clean_image_url(p["item"]["mediumImageUrls"][0]["imageUrl"])
                    )

        with tab2:
            url_in = st.text_input("楽天商品URL", key="u_t2")
            if st.button("情報取得", key="br_t2"):
                if "res2" in st.session_state: del st.session_state["res2"]
                res = requests.get(url_in, headers={'User-Agent': 'Mozilla/5.0'}).text
                t_m = re.search(r'<title>(.*?)</title>', res, re.DOTALL)
                i_m = re.search(r'<meta\s+property="og:image"\s+content="(.*?)"', res)
                st.session_state["it2"] = {
                    "name": t_m.group(1)[:50] if t_m else "商品",
                    "img": i_m.group(1) if i_m else "",
                    "url": url_in
                }
            if "it2" in st.session_state:
                it = st.session_state["it2"]
                st.image(it["img"], width=150)
                c1, c2, c3 = st.columns(3)
                with c1: gen_t2 = st.radio("性別", ["女性", "男性", "指定なし"], key="gen_t2")
                with c2: age_t2 = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="age_t2")
                with c3: kids_t2 = st.radio("子供", ["なし", "乳児", "幼児", "小学生"], key="kids_t2")
                tone_t2 = st.selectbox("トーン", ["エモい", "役立つ", "元気", "親近感", "本音レビュー", "あざと可愛い", "高級感", "ズボラ命"], key="tone_t2")
                len_t2 = st.slider("文字数", 10, 500, 50, step=10, key="len_t2")
                if st.button("✨ 本文作成", key="gen_btn_t2"):
                    with st.spinner("作成中..."):
                        st.session_state["gen_count"] += 1
                        st.session_state["res2"] = {"text": generate_post_text(
                            it["name"], "",
                            f"{gen_t2}, {','.join(age_t2)}, 子供:{kids_t2}",
                            tone_t2, len_t2, "", "", api["gemini"],
                            download_image(it["img"])
                        )}
                        st.rerun()
            if "res2" in st.session_state:
                show_final_ui(
                    "r2", st.session_state["res2"]["text"],
                    create_affiliate_link(st.session_state["it2"]["url"], api["rakuten_aff_id"]),
                    clean_image_url(st.session_state["it2"]["img"])
                )

        with tab3:
            img_url_t3 = st.text_input("🔗 画像URL", key="u_t3")
            hint_t3 = st.text_input("商品名ヒント", key="h_t3")
            if st.button("✨ 本文を作成", key="gen_btn_t3"):
                if "res3" in st.session_state: del st.session_state["res3"]
                if img_url_t3:
                    with st.spinner("解析中..."):
                        st.session_state["gen_count"] += 1
                        st.session_state["res3"] = {
                            "text": generate_post_text(hint_t3, "", "指定なし", "エモい", 50, "", "", api["gemini"], download_image(img_url_t3)),
                            "url": img_url_t3
                        }
                        st.rerun()
                else:
                    st.error("画像URLを入力してください。")
            if "res3" in st.session_state:
                aff_t3 = st.text_input("🔗 アフィ商品URL", key="aff_t3")
                show_final_ui(
                    "r3", st.session_state["res3"]["text"],
                    create_affiliate_link(aff_t3, api["rakuten_aff_id"]),
                    clean_image_url(st.session_state["res3"]["url"])
                )

# ==========================================
# --- 3. 分析 ---
# ==========================================
elif page == "3. エンゲージメント分析":
    st.title("🔍 分析")
    if not api["threads"]:
        st.warning("API設定を行ってください。")
    else:
        threads_data = get_threads_engagement(api["threads"])
        if threads_data:
            df = pd.DataFrame(threads_data)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            df = df[df['is_reply'] != True]
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("👀 閲覧", f"{df['views'].sum():,}")
            with c2: st.metric("❤️ いいね", f"{df['like_count'].sum():,}")
            with c3: st.metric("💬 返信", f"{df['reply_count'].sum():,}")
            st.dataframe(
                df[['timestamp', 'text', 'views', 'like_count', 'reply_count']].sort_values(by='views', ascending=False),
                use_container_width=True, hide_index=True
            )

# ==========================================
# --- 4. API設定 ---
# ==========================================
elif page == "4. API設定":
    st.title("⚙️ API設定")

    if st.session_state["loaded_user"]:
        st.success(f"✅ ログイン中: {st.session_state['loaded_user']}")

    tab_login, tab_register, tab_update = st.tabs(["🔑 ログイン", "🆕 新規登録", "🔄 API更新"])

    # ----------------------------------------
    # 🔑 ログインタブ
    # ----------------------------------------
    with tab_login:
        st.subheader("合言葉でログイン")
        st.caption("登録済みの合言葉を入力すると、APIキーが自動でロードされます。")
        pw_login = st.text_input("合言葉", type="password", key="pw_login")
        if st.button("🚀 ログイン", key="btn_login"):
            if pw_login:
                with st.spinner("照合中..."):
                    keys, uname = login_user(pw_login)
                if keys:
                    st.session_state["api_keys"].update(keys)
                    st.session_state["loaded_user"] = uname
                    st.success(f"✅ ようこそ、{uname} さん！")
                    st.rerun()
                else:
                    st.error("❌ 合言葉が違います。登録がまだの方は「新規登録」タブへ。")
            else:
                st.warning("合言葉を入力してください。")
        st.divider()
        if st.button("🚪 ログアウト（APIをクリア）", key="btn_logout"):
            st.session_state["api_keys"] = {
                "rakuten_id": "", "rakuten_key": "", "rakuten_aff_id": "",
                "gemini": "", "threads": "", "sheet_id": "", "g_json": ""
            }
            st.session_state["loaded_user"] = ""
            st.success("ログアウトしました。")
            st.rerun()

    # ----------------------------------------
    # 🆕 新規登録タブ
    # ----------------------------------------
    with tab_register:
        st.subheader("はじめての方：ユーザー登録")
        st.caption("自分で合言葉を決めて、APIキーと一緒に登録します。次回からは合言葉だけでログインできます。")
        reg_name = st.text_input("表示名（例：山田太郎）", key="reg_name")
        reg_pw   = st.text_input("合言葉（自分で決める・6文字以上）", type="password", key="reg_pw")
        reg_pw2  = st.text_input("合言葉（確認）", type="password", key="reg_pw2")
        st.divider()
        st.markdown("**APIキーを入力してください**")
        c1, c2 = st.columns(2)
        reg_rid  = c1.text_input("楽天 App ID",    type="password", key="reg_rid")
        reg_rkey = c1.text_input("楽天 Access Key", type="password", key="reg_rkey")
        reg_raff = c1.text_input("楽天 Aff ID",     type="password", key="reg_raff")
        reg_gem  = c2.text_input("Gemini API Key",  type="password", key="reg_gem")
        reg_thr  = c2.text_input("Threads Token",   type="password", key="reg_thr")
        reg_sid  = c2.text_input("Sheet ID",        key="reg_sid")
        reg_gjs  = st.text_area("GCloud JSON",      height=120, key="reg_gjs")
        if st.button("✅ 登録する", key="btn_register"):
            if not reg_name:
                st.error("表示名を入力してください。")
            elif len(reg_pw) < 6:
                st.error("合言葉は6文字以上にしてください。")
            elif reg_pw != reg_pw2:
                st.error("合言葉が一致しません。")
            elif not reg_thr:
                st.error("Threads Token は必須です。")
            else:
                api_data = {
                    "rakuten_id": reg_rid, "rakuten_key": reg_rkey,
                    "rakuten_aff_id": reg_raff, "gemini": reg_gem,
                    "threads": reg_thr, "sheet_id": reg_sid, "g_json": reg_gjs
                }
                with st.spinner("登録中..."):
                    ok = register_user(reg_name, reg_pw, api_data)
                if ok:
                    st.session_state["api_keys"].update(api_data)
                    st.session_state["loaded_user"] = reg_name
                    st.success("🎉 登録完了！次回からは「ログイン」タブで合言葉を入力するだけです。")
                    time.sleep(1)
                    st.rerun()

    # ----------------------------------------
    # 🔄 API更新タブ
    # ----------------------------------------
    with tab_update:
        st.subheader("登録済みAPIキーを更新")
        st.caption("合言葉を入力して、APIキーを上書き更新します。Threads Tokenの有効期限切れ時などに使用してください。")
        upd_pw = st.text_input("合言葉", type="password", key="upd_pw")
        st.markdown("**新しいAPIキーを入力してください**")
        c1, c2 = st.columns(2)
        upd_rid  = c1.text_input("楽天 App ID",    value=api["rakuten_id"],     type="password", key="upd_rid")
        upd_rkey = c1.text_input("楽天 Access Key", value=api["rakuten_key"],    type="password", key="upd_rkey")
        upd_raff = c1.text_input("楽天 Aff ID",     value=api["rakuten_aff_id"], type="password", key="upd_raff")
        upd_gem  = c2.text_input("Gemini API Key",  value=api["gemini"],         type="password", key="upd_gem")
        upd_thr  = c2.text_input("Threads Token",   value=api["threads"],        type="password", key="upd_thr")
        upd_sid  = c2.text_input("Sheet ID",        value=api["sheet_id"],       key="upd_sid")
        upd_gjs  = st.text_area("GCloud JSON",      value=api["g_json"],         height=120, key="upd_gjs")
        if st.button("🔄 更新する", key="btn_update"):
            if not upd_pw:
                st.error("合言葉を入力してください。")
            else:
                new_data = {
                    "rakuten_id": upd_rid, "rakuten_key": upd_rkey,
                    "rakuten_aff_id": upd_raff, "gemini": upd_gem,
                    "threads": upd_thr, "sheet_id": upd_sid, "g_json": upd_gjs
                }
                with st.spinner("更新中..."):
                    ok = update_user_api(upd_pw, new_data)
                if ok:
                    st.session_state["api_keys"].update(new_data)
                    st.success("✅ 更新完了！")
                    st.rerun()
                else:
                    st.error("❌ 合言葉が一致しません。")

# ==========================================
# --- 5. テンプレート管理 ---
# ==========================================
elif page == "5. テンプレート管理":
    st.title("📝 テンプレート管理")
    if not api["sheet_id"]:
        st.warning("API設定を行ってください。")
    else:
        with st.form("tf"):
            t_ti = st.text_input("テンプレート名")
            t_co = st.text_area("本文", height=150)
            if st.form_submit_button("保存"):
                if save_template(api["sheet_id"], api["g_json"], t_ti, t_co):
                    st.success("保存完了！")
                    time.sleep(1)
                    st.rerun()
        st.divider()
        templates = get_templates(api["sheet_id"], api["g_json"])
        for t in templates:
            with st.expander(t["title"]): st.write(t["content"])
