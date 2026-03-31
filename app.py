import streamlit as st
# ヘッダー、メニュー、フッターをすべて非表示にする設定

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .stAppDeployButton {display: none;}
            </style>
            """
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
    /* 👇 右上の「Fork」「GitHubアイコン」「3点リーダー」だけをピンポイントで消す */
    [data-testid="stToolbar"] { display: none !important; }
    .stAppDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }

    /* 👇 左側のメニュー（サイドバーや開閉ボタン）を絶対に強制表示させる安全策 */
    header { visibility: visible !important; background: transparent !important; }
    [data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; }
    [data-testid="stSidebar"] { display: block !important; visibility: visible !important; }

    /* 👇 以下の既存デザインはそのまま維持 */
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
    .ranking-rank { font-size: 20px; font-weight: 900; color: #007AFF; margin-right: 10px; }
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

# 💡【修正】strict=False を追加してJSONの改行エラーを回避
def save_to_sheets(sheet_id, g_json, row_data):
    if not sheet_id or not g_json: return False
    try:
        creds = Credentials.from_service_account_info(json.loads(g_json, strict=False), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gspread.authorize(creds).open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"スプレッドシート書き込みエラー: {e}")
        return False

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
        try: 
            ws = ss.worksheet("テンプレート")
        except: 
            ws = ss.add_worksheet(title="テンプレート", rows=100, cols=2)
            ws.append_row(["タイトル", "本文"])
        ws.append_row([title, content])
        return True
    except Exception as e:
        st.error(f"テンプレート保存エラー: {e}")
        return False

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
    
    # 👇 ここからプロンプトを「劇的改善版」に変更
    prompt = f"""あなたは、SNSでリアルな本音を発信するインフルエンサーです。
以下の楽天商品「{item_name}」{price_str}を、ターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字でつぶやいてください。

【絶対厳守のルール】
1. 宣伝・紹介っぽさを完全に消し、自分が実際に使って感動した「リアルな本音・独り言」として書くこと。
2. 以下の「AI特有の不自然な表現」は絶対に使用禁止。
   （禁止ワード：〜をご存知ですか、結論から言うと、〜ですよね、ぜひチェックして、いかがでしたか、快適な生活を）
3. カタログスペックを並べるのではなく、「これのおかげで生活がどう変わるか（情景・感情）」を1点だけ強烈にアピールすること。
4. 全部を説明しきらず、読者が思わず「え、なにそれ？」「詳しく見たい！」と画像をタップしたくなる『余白（フック）』を残すこと。
5. 文末の句点は適度に省き、SNSらしい自然な改行や「ガチで」「やばい」などの口語表現を許可します。
"""
    
    if reference_post: 
        prompt += f"\n【参考にするバズ投稿の型（この文体を真似てください）】\n{reference_post}\n"
    if custom_prompt: 
        prompt += f"\n【特別指示】\n{custom_prompt}"
    
    # 👇 ここから下の「503エラー自動リトライ機能」はそのまま維持
    for attempt in range(3):
        try:
            client = genai.Client(api_key=api_key)
            contents = [prompt, image] if image else prompt
            response = client.models.generate_content(model='gemini-2.5-flash', contents=contents)
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg and attempt < 2:
                time.sleep(3)
                continue
            return f"❌ AIエラー発生: {err_msg}"
    return "❌ サーバーエラー"

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
# 🖥️ メイン画面構成
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {
        "rakuten_id": "", "rakuten_key": "", "rakuten_aff_id": "", 
        "gemini": "", "threads": "", "sheet_id": "", "g_json": ""
    }

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. エンゲージメント分析", "4. API設定", "5. テンプレート管理"])

# ==========================================
# 📊 1. ダッシュボード
# ==========================================
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    api = st.session_state["api_keys"]

    if not api["sheet_id"] or not api["threads"]:
        st.info("💡 API設定でロードを行うと、ここにダッシュボードが表示されます。")
    else:
        st.subheader("📅 本日の投稿予定")
        sheet_data = get_sheet_data(api["sheet_id"], api["g_json"])
        today_str = datetime.now().strftime('%Y/%m/%d')
        
        if sheet_data:
            today_pending = [r for r in sheet_data if r.get("投稿チェック", "") in ["pending", "予約中", ""] and r.get("投稿日", "") == today_str]
            if today_pending:
                preview_list = []
                for p in today_pending:
                    dt_str = f"{p.get('時','')}:{p.get('分','')}"
                    preview_list.append({"予定時間": dt_str, "本文プレビュー": p.get('本文', '')[:40] + "..."})
                st.dataframe(preview_list, use_container_width=True, hide_index=True)
            else:
                st.success("本日の待機中の投稿はありません。")

        st.divider()
        st.subheader("📈 アカウント総合状況 (直近100件)")
        threads_data = get_threads_engagement(api["threads"])
        
        if threads_data:
            df = pd.DataFrame(threads_data)
            for col in ['like_count', 'reply_count', 'views']:
                if col not in df.columns: df[col] = 0
            if 'text' not in df.columns: df['text'] = ""
            if 'timestamp' not in df.columns: df['timestamp'] = datetime.now().isoformat()
            if 'is_reply' not in df.columns: df['is_reply'] = False

            df['like_count'] = pd.to_numeric(df['like_count'], errors='coerce').fillna(0).astype(int)
            df['reply_count'] = pd.to_numeric(df['reply_count'], errors='coerce').fillna(0).astype(int)
            df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0).astype(int)
            df['date_key'] = pd.to_datetime(df['timestamp']).dt.strftime('%m/%d')
            
            df_main = df[df['is_reply'] != True]
            df_main = df_main[~df_main['text'].astype(str).str.contains("▼ 詳細はこちら", na=False)]

            total_posts = len(df_main)
            total_likes = df_main['like_count'].sum()
            total_replies = df_main['reply_count'].sum()

            c1, c2, c3 = st.columns(3)
            with c1: 
                st.metric("📝 累計投稿数", f"{total_posts} 件")
                st.bar_chart(df_main.groupby('date_key').size(), use_container_width=True)
            with c2: 
                st.metric("❤️ 累計いいね数", f"{total_likes:,} 回")
                st.bar_chart(df_main.groupby('date_key')['like_count'].sum(), use_container_width=True, color="#FF4B4B")
            with c3: 
                st.metric("💬 累計リプライ", f"{total_replies:,} 件")
                st.bar_chart(df_main.groupby('date_key')['reply_count'].sum(), use_container_width=True, color="#FFB800")

# ==========================================
# 🛒 2. 商品作成＆予約ページ
# ==========================================
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"] or not api["gemini"]: 
        st.warning("API設定を先に済ませてください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキングから", "🔗 URLから", "📸 画像から"])

        def draw_ui(k):
            c1, c2, c3 = st.columns(3)
            with c1: gen = st.radio("性別", ["女性", "男性", "指定なし"], key=f"r_gen_{k}")
            with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key=f"m_age_{k}")
            with c3: kids = st.radio("子供", ["なし", "あり"], key=f"r_kids_{k}")
            
            c4, c5 = st.columns(2)
            tone_list = ["エモい", "役立つ", "元気", "親近感", "本音レビュー風", "専門家", "ユーモア", "あざと可愛い", "高級感", "ズボラ命"]
            with c4: tone = st.selectbox("トーン", tone_list, key=f"s_tone_{k}")
            with c5: length = st.slider("文字数", 10, 500, 50, step=10, key=f"s_len_{k}")
            
            tmp_opt = ["手動入力"] + [t["title"] for t in templates]
            sel_tmp = st.selectbox("🧠 テンプレート適用", tmp_opt, key=f"tmp_{k}")
            ref = next((t["content"] for t in templates if t["title"] == sel_tmp), "") if sel_tmp != "手動入力" else ""
            custom_prompt = st.text_area("✍️ 自由な追加指示 (オプション)", key=f"c_prompt_{k}")
            return f"{gen}, 年代:{','.join(age)}, 子供:{kids}", tone, length, ref, custom_prompt

        def show_final_ui(key, default_txt, default_url, default_img_url):
            with st.expander("✨ 生成結果の確認・編集", expanded=True):
                use_img = st.checkbox("🖼️ 投稿に画像を含める", value=True, key=f"use_img_{key}")
                drive_url = st.text_input("🔗 投稿用画像URL (Googleドライブ等: 空欄なら初期画像を引用)", value=default_img_url if default_img_url else "", key=f"drive_{key}")
                
                mk, rk = f"m_txt_{key}", f"r_txt_{key}"
                if mk not in st.session_state: st.session_state[mk] = default_txt
                if rk not in st.session_state: st.session_state[rk] = f"▼ 詳細はこちら\n{default_url}"
                
                m_txt = st.text_area("本文", key=mk, height=150)
                r_txt = st.text_area("リプライ (URL等)", key=rk, height=80)
                
                final_img = None
                if use_img:
                    final_img = convert_drive_link(drive_url) if drive_url else default_img_url
                
                c_now, c_sch = st.columns(2)
                if c_now.button("🚀 即時投稿", key=f"btn_now_{key}"):
                    mid = post_to_threads(api["threads"], st.session_state[mk], image_url=final_img)
                    if mid:
                        time.sleep(5)
                        post_to_threads(api["threads"], st.session_state[rk], reply_to_id=mid)
                        st.success("成功！")
                
                with c_sch:
                    d = st.date_input("予約日", key=f"d_in_{key}")
                    t = st.time_input("時間", key=f"t_in_{key}")
                    if st.button("🗓️ 予約リストに追加", key=f"reserve_{key}"):
                        row = ["", st.session_state[mk], d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", st.session_state[rk], final_img if final_img else ""]
                        if save_to_sheets(api["sheet_id"], api["g_json"], row):
                            st.success(f"✅ 保存しました！")

        with tab1:
            genres_dict = {
                "🏆 総合ランキング": "0", "👗 レディースファッション": "100371", "👔 メンズファッション": "551177",
                "👜 バッグ・小物": "216129", "👟 靴": "558885", "⌚ 腕時計": "558929",
                "💎 ジュエリー": "200162", "💄 美容・コスメ": "100939", "💊 ダイエット・健康": "100143",
                "🏥 医薬品・介護": "551169", "🍎 食品": "100227", "🍪 スイーツ・お菓子": "551167",
                "🍹 水・ドリンク": "100316", "🍺 ビール・洋酒": "510915", "🍶 日本酒・焼酎": "510901",
                "🛋 インテリア・収納": "100804", "🍳 キッチン・食器": "558944", "🧼 日用品・手芸": "215783",
                "🔌 家電": "562631", "📸 カメラ": "211742", "💻 パソコン": "100026",
                "📱 スマホ": "562637", "⚽ スポーツ": "101070", "⛳ ゴルフ用品": "101077",
                "🚗 車・バイク": "503190", "🧸 おもちゃ": "101164", "🎨 ホビー": "101165",
                "🎸 楽器": "112493", "🐱 ペット": "101213", "🍼 キッズ・ベビー": "100533",
                "📚 本・雑誌": "200376", "📀 CD・DVD": "101240", "🎮 TVゲーム": "101205"
            }
            sel_name = st.selectbox("ジャンルを選択", list(genres_dict.keys()), key="sel_g_t1")
            if st.button("ランキング取得", key="get_rank_t1"):
                st.session_state["items_t1"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres_dict[sel_name])
                if "res_list_t1" in st.session_state: del st.session_state["res_list_t1"]

            if "items_t1" in st.session_state:
                selected = []
                for i, item in enumerate(st.session_state["items_t1"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        c2.write(f"**{item['itemName'][:50]}...**")
                        if c2.checkbox("選ぶ", key=f"chk_t1_{i}"):
                            item["u_img"] = c2.file_uploader("📸 スクショ添付 (AI解析用)", type=["jpg","png"], key=f"uf_t1_{i}")
                            selected.append(item)
                
                if selected:
                    st.divider()
                    t_str, tone, length, ref, cp = draw_ui("t1")
                    if st.button(f"✨ {len(selected)}件を一括生成", key="gen_t1"):
                        res_list = []
                        pb = st.progress(0)
                        for j, s_item in enumerate(selected):
                            img_obj = Image.open(s_item["u_img"]) if s_item["u_img"] else download_image(s_item["mediumImageUrls"][0]["imageUrl"])
                            txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], t_str, tone, length, cp, ref, api["gemini"], img_obj)
                            res_list.append({"item": s_item, "text": txt})
                            pb.progress((j+1)/len(selected))
                        st.session_state["res_list_t1"] = res_list

            if "res_list_t1" in st.session_state:
                for k, p in enumerate(st.session_state["res_list_t1"]):
                    item = p["item"]
                    aff_url = create_affiliate_link(item.get("itemUrl", ""), str(api["rakuten_aff_id"]).strip())
                    show_final_ui(f"r1_{item['itemCode']}", p["text"], aff_url, item["mediumImageUrls"][0]["imageUrl"])

        with tab2:
            url_in = st.text_input("楽天商品URLを貼り付け", key="url_in_t2")
            if st.button("情報を取得", key="fetch_t2"):
                res = requests.get(url_in, headers={'User-Agent': 'Mozilla/5.0'})
                t_m = re.search(r'<title>(.*?)</title>', res.text, re.DOTALL)
                i_m = re.search(r'<meta\s+property="og:image"\s+content="(.*?)"', res.text)
                st.session_state["item_t2"] = {"name": t_m.group(1)[:50] if t_m else "商品", "img": i_m.group(1) if i_m else "", "url": url_in}
            
            if "item_t2" in st.session_state:
                it = st.session_state["item_t2"]
                st.image(it["img"], width=150)
                t_str, tone, length, ref, cp = draw_ui("t2")
                if st.button("✨ 本文作成", key="gen_t2"):
                    txt = generate_post_text(it["name"], "", t_str, tone, length, cp, ref, api["gemini"], download_image(it["img"]))
                    st.session_state["res_t2"] = {"text": txt}
            
            if "res_t2" in st.session_state:
                aff_url_t2 = create_affiliate_link(st.session_state["item_t2"]["url"], str(api["rakuten_aff_id"]).strip())
                show_final_ui("res_t2_final", st.session_state["res_t2"]["text"], aff_url_t2, st.session_state["item_t2"]["img"])

        with tab3:
            st.info("💡 画像URLを読み込ませて本文を作成し、投稿します。時間がかかる、混雑時はエラーになる場合があります。")
            img_url_t3 = st.text_input("🔗 画像URLを入力 (Googleドライブ等)", key="url_tab3")
            hint_t3 = st.text_input("商品名のヒント (任意)", key="hint_tab3")
            t_str, tone, length, ref, cp = draw_ui("t3")
            
            if st.button("✨ 本文を作成する", key="gen_t3"):
                if img_url_t3 or hint_t3:
                    ana_img = download_image(img_url_t3)
                    txt = generate_post_text(hint_t3, "", t_str, tone, length, cp, ref, api["gemini"], ana_img)
                    st.session_state["res_t3"] = {"text": txt, "url": img_url_t3}
                else:
                    st.error("画像URLかヒントを入力してください。")
            
            if "res_t3" in st.session_state:
                uf_t3 = st.file_uploader("📸 【追加】投稿用スクショ添付 (無ければ上記URLを使用)", type=["jpg","png"], key="uf_t3")
                aff_t3 = st.text_input("🔗 アフィリエイト商品URL (リプライ用)", key="aff_url_t3")
                final_reply_url = create_affiliate_link(aff_t3, str(api["rakuten_aff_id"]).strip()) if aff_t3 else "【URL未設定】"
                show_final_ui("res_t3_final", st.session_state["res_t3"]["text"], final_reply_url, st.session_state["res_t3"]["url"])

# ==========================================
# 🔍 3. エンゲージメント分析
# ==========================================
elif page == "3. エンゲージメント分析":
    st.title("🔍 エンゲージメント分析")
    api = st.session_state["api_keys"]

    if not api["threads"]:
        st.info("💡 API設定でロードを行ってください。")
    else:
        threads_data = get_threads_engagement(api["threads"])
        if threads_data:
            df = pd.DataFrame(threads_data)
            for col in ['like_count', 'reply_count', 'views']:
                if col not in df.columns: df[col] = 0
            if 'text' not in df.columns: df['text'] = ""
            if 'timestamp' not in df.columns: df['timestamp'] = datetime.now().isoformat()
            if 'is_reply' not in df.columns: df['is_reply'] = False

            df['like_count'] = pd.to_numeric(df['like_count'], errors='coerce').fillna(0).astype(int)
            df['reply_count'] = pd.to_numeric(df['reply_count'], errors='coerce').fillna(0).astype(int)
            df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0).astype(int)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            
            df = df[df['is_reply'] != True]
            df = df[~df['text'].astype(str).str.contains("▼ 詳細はこちら", na=False)]

            st.subheader("📊 累計パフォーマンス")

            total_likes = df['like_count'].sum()
            total_views = df['views'].sum()
            total_replies = df['reply_count'].sum()

            c1, c2, c3 = st.columns(3)
            with c1: st.metric("👀 累計閲覧数", f"{total_views:,}")
            with c2: st.metric("❤️ 累計いいね数", f"{total_likes:,}")
            with c3: st.metric("💬 累計コメント数", f"{total_replies:,}")

            st.divider()

            st.subheader("📑 過去の投稿一覧 (全データ)")
            display_df = df[['timestamp', 'text', 'views', 'like_count', 'reply_count']].copy()
            display_df.columns = ['投稿日', '投稿内容', '👀 閲覧数', '❤️ いいね', '💬 コメント']
            display_df['投稿内容'] = display_df['投稿内容'].apply(lambda x: str(x)[:60] + '...' if len(str(x)) > 60 else x)
            st.dataframe(display_df.sort_values(by='投稿日', ascending=False), use_container_width=True, hide_index=True)

# ==========================================
# ⚙️ 4. API設定
# ==========================================
elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード", expanded=True):
        pw = st.text_input("合言葉", type="password", key="master_pw_input")
        if st.button("ロード", key="load_btn"):
            secret_pw = st.secrets.get("master_password")
            if pw == secret_pw:
                st.session_state["f_ri"] = st.secrets.get("rakuten_id", "")
                st.session_state["f_rk"] = st.secrets.get("rakuten_key", "")
                st.session_state["f_ra"] = st.secrets.get("rakuten_aff_id", "")
                st.session_state["f_gk"] = st.secrets.get("gemini_key", "")
                st.session_state["f_tt"] = st.secrets.get("threads_token", "")
                st.session_state["f_si"] = st.secrets.get("sheet_id", "")
                st.session_state["f_gj"] = st.secrets.get("g_json", "")
                st.success("✅ ロード成功！下の入力欄に反映されました。「設定を保存」を押してください。")
            else:
                st.error("❌ 合言葉が違います")

    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天 App ID", type="password", key="f_ri")
        r_key = c1.text_input("楽天 Access Key", type="password", key="f_rk")
        r_aff = c1.text_input("楽天 アフィリエイトID (任意)", type="password", key="f_ra")
        
        g_key = c2.text_input("Gemini API", type="password", key="f_gk")
        t_tok = c2.text_input("Threads Token", type="password", key="f_tt")
        s_id = c2.text_input("Sheet ID", key="f_si")
        g_js = st.text_area("JSON", height=100, key="f_gj")
        
        if st.button("設定を保存", key="f_save_btn"):
            st.session_state["api_keys"].update({
                "rakuten_id":r_id, "rakuten_key":r_key, "rakuten_aff_id":r_aff, 
                "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js
            })
            st.success("設定を保存しました！")

# ==========================================
# 💡 5. テンプレート管理
# ==========================================
elif page == "5. テンプレート管理":
    st.title("📝 テンプレート管理")
    api = st.session_state["api_keys"]
    
    if not api["sheet_id"]:
        st.warning("⚠️ API設定画面で設定をロードまたは保存してから開いてください。")
    else:
        with st.form("template_form"):
            st.subheader("➕ 新規テンプレート登録")
            t_title = st.text_input("テンプレート名 (例: バズテンプレA)")
            t_content = st.text_area("バズ投稿の本文 (これを手本にします)", height=150)
            
            if st.form_submit_button("保存する"):
                if not t_title or not t_content:
                    st.error("❌ タイトルと本文を入力してください。")
                else:
                    if save_template(api["sheet_id"], api["g_json"], t_title, t_content):
                        st.success("✅ テンプレートを保存しました！")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ 保存に失敗しました。JSONの形式が正しくない可能性があります。")

        st.divider()
        st.subheader("📚 登録済みのテンプレート")
        templates = get_templates(api["sheet_id"], api["g_json"])
        if templates:
            for t in templates:
                with st.expander(t["title"]):
                    st.write(t["content"])
        else:
            st.info("登録されているテンプレートはありません。")
