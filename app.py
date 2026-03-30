import streamlit as st
import requests
from google import genai
import time
from PIL import Image
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import concurrent.futures
import re
import urllib.parse

# ==========================================
# 🎨 デザイナー設計：モダンUI & 不要メニュー非表示
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
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .stButton>button { 
        background-color: #007AFF !important; color: #FFFFFF !important; font-weight: bold; 
        border-radius: 8px; width: 100%; border: none; padding: 0.5rem 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群
# ==========================================
def save_to_sheets(sheet_id, g_json, row_data):
    if not sheet_id or not g_json: return False
    try:
        creds_dict = json.loads(g_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except: return False

def get_sheet_data(sheet_id, g_json):
    if not sheet_id or not g_json: return []
    try:
        creds_dict = json.loads(g_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        data = client.open_by_key(sheet_id).sheet1.get_all_values()
        if len(data) < 2: return []
        headers = data[0]
        return [dict(zip(headers, row)) for row in data[1:] if any(row)]
    except: return []

def get_templates(sheet_id, g_json):
    if not sheet_id or not g_json: return []
    try:
        creds_dict = json.loads(g_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        ss = client.open_by_key(sheet_id)
        try: ws = ss.worksheet("テンプレート")
        except: return []
        data = ws.get_all_values()
        return [{"title": row[0], "content": row[1]} for row in data[1:] if len(row) >= 2 and row[0]]
    except: return []

def save_template(sheet_id, g_json, title, content):
    if not sheet_id or not g_json: return False
    try:
        creds_dict = json.loads(g_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        ss = client.open_by_key(sheet_id)
        try: ws = ss.worksheet("テンプレート")
        except: ws = ss.add_worksheet(title="テンプレート", rows="100", cols="2")
        ws.append_row([title, content])
        return True
    except: return False

def get_threads_engagement(token):
    if not token: return []
    url = f"https://graph.threads.net/v1.0/me/threads?fields=id,text,timestamp,is_reply&limit=30&access_token={token}"
    try:
        res = requests.get(url).json()
        threads = res.get("data", [])
        def fetch_insights(thread):
            t_id = thread['id']
            ins_url = f"https://graph.threads.net/v1.0/{t_id}/insights?metric=views,likes,replies&access_token={token}"
            try:
                ins_res = requests.get(ins_url).json()
                metrics = {d['name']: d['values'][0]['value'] for d in ins_res.get("data", [])}
                thread.update({'views': metrics.get('views', 0), 'likes': metrics.get('likes', 0), 'replies': metrics.get('replies', 0)})
            except: thread.update({'views': 0, 'likes': 0, 'replies': 0})
            return thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
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

def get_item_info_from_url(url):
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        html = res.text
        t_m = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
        title = t_m.group(1).replace("【楽天市場】", "").split("：")[0].strip() if t_m else ""
        i_m = re.search(r'<meta\s+property="og:image"\s+content="(.*?)"', html)
        image = i_m.group(1) if i_m else ""
        return {"itemName": title[:100], "imageUrl": image, "itemUrl": url}
    except: return {"itemName": "", "imageUrl": "", "itemUrl": url}

def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    client = genai.Client(api_key=api_key)
    subject = f"「{item_name}」" if item_name else "添付画像の商品"
    prompt = f"""{subject}をターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介してください。
【絶対条件】
・本文のみを出力。画像がある場合はその内容を必ず反映させること。
"""
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
# 🖥️ メイン構成
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"","rakuten_key":"","rakuten_aff_id":"","gemini":"","threads":"","sheet_id":"","g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. 分析", "4. API設定", "5. テンプレート管理"])

tone_list = ["エモい", "役立つ", "元気", "親近感", "本音レビュー風", "あざと可愛い", "高級感", "ユーモア"]

# ------------------------------------------
# 📊 1. ダッシュボード
# ------------------------------------------
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    api = st.session_state["api_keys"]
    if not api["sheet_id"]: st.info("API設定を完了すると、ここに予定が表示されます。")
    else:
        st.subheader("📅 本日の投稿予定")
        data = get_sheet_data(api["sheet_id"], api["g_json"])
        today = datetime.now().strftime('%Y/%m/%d')
        today_list = [r for r in data if r.get('投稿日') == today]
        if today_list: st.dataframe(pd.DataFrame(today_list)[['時', '分', '本文']], use_container_width=True)
        else: st.success("本日の投稿予定はありません。")
        
        st.divider()
        st.subheader("📈 アカウント概況")
        stats = get_threads_engagement(api["threads"])
        if stats:
            df = pd.DataFrame(stats)
            c1, c2, c3 = st.columns(3)
            c1.metric("👀 累計閲覧", f"{df['views'].sum():,}")
            c2.metric("❤️ いいね", f"{df['likes'].sum():,}")
            c3.metric("💬 返信", f"{df['replies'].sum():,}")

# ------------------------------------------
# 🛒 2. 商品作成＆予約
# ------------------------------------------
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["gemini"]: st.warning("API設定を先に済ませてください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキング", "🔗 URLから", "📸 画像/スクショから"])

        def draw_settings(suffix):
            c1, c2 = st.columns(2)
            with c1: 
                gender = st.radio("性別", ["女性", "男性", "指定なし"], key=f"gen_{suffix}")
                age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key=f"age_{suffix}")
            with c2:
                tone = st.selectbox("トーン", tone_list, key=f"tone_{suffix}")
                length = st.slider("文字数", 20, 400, 80, key=f"len_{suffix}")
            temp_opt = ["手動入力"] + [t["title"] for t in templates]
            sel_temp = st.selectbox("🧠 テンプレート", temp_opt, key=f"temp_{suffix}")
            ref = next((t["content"] for t in templates if t["title"] == sel_temp), "") if sel_temp != "手動入力" else ""
            ref_post = st.text_area("🧠 参考投稿", value=ref, key=f"ref_area_{suffix}")
            custom = st.text_area("✍️ 自由指示", key=f"custom_{suffix}")
            return f"{gender}, {','.join(age)}", tone, length, ref_post, custom

        def show_result(res_key, default_url, default_img):
            if res_key in st.session_state:
                p = st.session_state[res_key]
                with st.container(border=True):
                    m_key, r_key = f"fm_{res_key}", f"fr_{res_key}"
                    if m_key not in st.session_state: st.session_state[m_key] = p["text"]
                    if r_key not in st.session_state: st.session_state[r_key] = f"▼ 詳細はこちら\n{default_url}"
                    st.text_area("本文編集", key=m_key, height=150)
                    st.text_area("リプライ編集", key=r_key, height=80)
                    c_now, c_res = st.columns(2)
                    if c_now.button("🚀 即時投稿", key=f"now_{res_key}"):
                        mid = post_to_threads(api["threads"], st.session_state[m_key], image_url=default_img)
                        if mid:
                            time.sleep(5); post_to_threads(api["threads"], st.session_state[r_key], reply_to_id=mid)
                            st.success("完了！")
                    with c_res:
                        d_v = st.date_input("予約日", key=f"d_{res_key}")
                        t_v = st.time_input("時間", key=f"t_{res_key}")
                        if st.button("🗓️ 予約登録", key=f"btn_res_{res_key}"):
                            row = ["", st.session_state[m_key], d_v.strftime('%Y/%m/%d'), str(t_v.hour), str(t_v.minute), "pending", "", "", st.session_state[r_key], default_img]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row): st.success("予約完了！")

        with tab1:
            # ほぼすべての主要ジャンルを網羅
            genres_dict = {
                "🏆 総合": "0", "💄 美容・コスメ": "100939", "👗 レディースファッション": "100371",
                "👔 メンズファッション": "551177", "🍎 食品": "100227", "🍪 スイーツ・お菓子": "551167",
                "🍹 水・ソフトドリンク": "100316", "🍺 ビール・洋酒": "510915", "🍶 日本酒・焼酎": "510901",
                "🔌 家電": "562631", "📸 カメラ・スマホ": "211742", "🛋 インテリア・収納": "100804",
                "🍳 キッチン・調理器具": "558944", "🛁 日用品雑貨": "215783", "🍼 キッズ・ベビー": "100533",
                "🐱 ペット用品": "101213", "⚽ スポーツ・アウトドア": "101070", "⛳ ゴルフ用品": "101077",
                "🚗 車・バイク用品": "503190", "🧸 おもちゃ・ホビー": "101164", "🎮 ゲーム": "101205",
                "📚 本・雑誌": "200376", "📀 CD・DVD": "101240", "💎 ジュエリー": "200162",
                "👟 靴": "558885", "👜 バッグ・ブランド": "216129", "⌚ 腕時計": "558929"
            }
            sel_g = st.selectbox("ジャンルを選択", list(genres_dict.keys()), key="rank_sel_final")
            if st.button("ランキングを取得", key="btn_rank_fetch_final"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres_dict[sel_g])
            
            if "items" in st.session_state:
                for i, item in enumerate(st.session_state["items"]):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    if c2.button(f"選ぶ: {item['itemName'][:40]}...", key=f"sel_r_{i}"):
                        st.session_state["active_item"] = item
                if "active_item" in st.session_state:
                    st.divider(); t_str, tone, length, ref, custom = draw_settings("tab1")
                    if st.button("✨ 本文作成", key="gen_btn_tab1_f"):
                        it = st.session_state["active_item"]
                        txt = generate_post_text(it["itemName"], it["itemPrice"], t_str, tone, length, custom, ref, api["gemini"])
                        st.session_state["res1"] = {"text": txt}
                    show_result("res1", st.session_state["active_item"]["itemUrl"], st.session_state["active_item"]["mediumImageUrls"][0]["imageUrl"])

        with tab2:
            url_in = st.text_input("楽天URL", key="url_in_v3")
            if st.button("情報を取得", key="btn_url_v3"):
                st.session_state["url_info"] = get_item_info_from_url(url_in)
            if "url_info" in st.session_state:
                info = st.session_state["url_info"]
                st.image(info["imageUrl"], width=150); st.write(info["itemName"])
                t_str, tone, length, ref, custom = draw_settings("tab2")
                if st.button("✨ 本文作成", key="gen_btn_tab2_f"):
                    txt = generate_post_text(info["itemName"], "", t_str, tone, length, custom, ref, api["gemini"])
                    st.session_state["res2"] = {"text": txt}
                show_result("res2", info["itemUrl"], info["imageUrl"])

        with tab3:
            u_img = st.file_uploader("スクショ/画像をアップ", type=["jpg","png","webp"], key="up_tab3_f")
            hint = st.text_input("商品名/ヒント", key="hint_tab3_f")
            t_str, tone, length, ref, custom = draw_settings("tab3")
            if st.button("✨ 解析して本文作成", key="gen_btn_tab3_f"):
                if u_img:
                    txt = generate_post_text(hint, "", t_str, tone, length, custom, ref, api["gemini"], image=Image.open(u_img))
                    st.session_state["res3"] = {"text": txt}
                else: st.error("画像が必要です")
            show_result("res3", "【URLを貼り付け】", "")

# ------------------------------------------
# 🔍 3. 分析
# ------------------------------------------
elif page == "3. 分析":
    st.title("🔍 エンゲージメント分析")
    api = st.session_state["api_keys"]
    if api["threads"]:
        stats = get_threads_engagement(api["threads"])
        if stats:
            df = pd.DataFrame(stats)[['timestamp', 'text', 'views', 'likes', 'replies']]
            df.columns = ['投稿日時', '内容', '👀 閲覧', '❤️ いいね', '💬 返信']
            st.dataframe(df.sort_values('👀 閲覧', ascending=False), use_container_width=True)

# ------------------------------------------
# ⚙️ 4. API設定
# ------------------------------------------
elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード (ロード)", expanded=True):
        admin_pw = st.text_input("合言葉", type="password", key="pw_v3")
        if st.button("Secretsからロード"):
            if admin_pw == st.secrets.get("master_password"):
                st.session_state["api_ri"] = st.secrets.get("rakuten_id", "")
                st.session_state["api_rk"] = st.secrets.get("rakuten_key", "")
                st.session_state["api_ra"] = st.secrets.get("rakuten_aff_id", "")
                st.session_state["api_gk"] = st.secrets.get("gemini_key", "")
                st.session_state["api_tt"] = st.secrets.get("threads_token", "")
                st.session_state["api_si"] = st.secrets.get("sheet_id", "")
                st.session_state["api_gj"] = st.secrets.get("g_json", "")
                st.success("ロード完了！保存をクリックしてください。")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天ID", key="api_ri", type="password")
        r_key = c1.text_input("楽天Key", key="api_rk", type="password")
        r_aff = c1.text_input("楽天Aff", key="api_ra", type="password")
        g_key = c2.text_input("Gemini API", key="api_gk", type="password")
        t_tok = c2.text_input("Threads Token", key="api_tt", type="password")
        s_id = c2.text_input("Sheet ID", key="api_si")
        g_js = st.text_area("JSON", key="api_gj", height=100)
        if st.button("設定を保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "rakuten_aff_id":r_aff, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("保存完了！")

# ------------------------------------------
# 📝 5. テンプレート管理
# ------------------------------------------
elif page == "5. テンプレート管理":
    st.title("📝 テンプレート管理")
    api = st.session_state["api_keys"]
    if api["sheet_id"]:
        with st.form("temp_v3"):
            t_title = st.text_input("テンプレート名")
            t_content = st.text_area("本文型")
            if st.form_submit_button("保存"):
                if save_template(api["sheet_id"], api["g_json"], t_title, t_content):
                    st.success("保存完了！"); time.sleep(1); st.rerun()
        st.divider()
        for t in get_templates(api["sheet_id"], api["g_json"]):
            with st.expander(t["title"]): st.write(t["content"])
