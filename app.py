import streamlit as st
import requests
from google import genai
import time
from PIL import Image
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import concurrent.futures
import re
import urllib.parse

# ==========================================
# 🎨 デザイナー設計：テーマ対応のモダンUI（デザイン完全復活版）
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* 不要な要素の非表示 */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display: none;}

    /* 全体のフォントとレイアウト */
    .stApp { font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif; }
    
    /* カードデザイン（影とホバー） */
    [data-testid="stVerticalBlockBorderWrapper"] { 
        border-radius: 12px; padding: 20px; margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: transform 0.2s ease, box-shadow 0.2s ease;
        background-color: #ffffff;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.08);
    }

    /* ボタンデザイン */
    .stButton>button { 
        background-color: #007AFF !important; color: #FFFFFF !important; font-weight: bold; 
        border-radius: 8px; width: 100%; border: none; padding: 0.6rem 1rem; transition: all 0.2s;
    }
    .stButton>button:hover { background-color: #0056b3 !important; transform: scale(1.02); }

    /* メトリクス（数字）の強調 */
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; font-weight: 800 !important; color: #007AFF !important; }
    [data-testid="stMetricLabel"] { font-size: 1.1rem !important; font-weight: 600 !important; }

    /* ランキングボックスの装飾 */
    .ranking-box {
        border-left: 6px solid #007AFF; border-radius: 10px; 
        padding: 18px 22px; margin-bottom: 15px; background-color: rgba(0, 122, 255, 0.04);
        border-top: 1px solid rgba(0,0,0,0.05); border-right: 1px solid rgba(0,0,0,0.05); border-bottom: 1px solid rgba(0,0,0,0.05);
    }
    .ranking-rank { font-size: 22px; font-weight: 900; color: #007AFF; margin-right: 12px; }
    .stat-badge { 
        display: inline-block; background: rgba(128,128,128, 0.12); padding: 5px 12px; 
        border-radius: 20px; font-size: 13px; font-weight: bold; margin-right: 10px; color: #4B5563;
    }
    [data-testid="stTabs"] button { font-size: 17px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群（スプレッドシート・Threads・楽天・AI）
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
        return [dict(zip(data[0], row)) for row in data[1:] if any(row)]
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
    url = f"https://graph.threads.net/v1.0/me/threads?fields=id,text,timestamp,is_reply&limit=100&access_token={token}"
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
    prompt = f"""{subject}をターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介。画像解析も重視。本文のみ。"""
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
# 🖥️ サイドバー・共通設定
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"","rakuten_key":"","rakuten_aff_id":"","gemini":"","threads":"","sheet_id":"","g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. 分析", "4. API設定", "5. テンプレート管理"])
tone_list = ["エモい", "役立つ", "元気", "親近感", "本音レビュー風", "あざと可愛い", "高級感", "ズボラ命"]

# ------------------------------------------
# 📊 1. ダッシュボード (デザイン復活版)
# ------------------------------------------
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    api = st.session_state["api_keys"]
    if not api["threads"]: st.info("💡 API設定を完了すると、ここに統計が表示されます。")
    else:
        with st.spinner("データを取得中..."):
            raw = get_threads_engagement(api["threads"])
            if raw:
                df = pd.DataFrame(raw)
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
                
                # 大きな数字とグラフの3カラム
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("📝 累計投稿数", f"{len(df)} 件")
                    st.bar_chart(df.groupby('timestamp').size(), use_container_width=True)
                with c2:
                    st.metric("❤️ 累計いいね数", f"{df['likes'].sum():,} 回")
                    st.bar_chart(df.groupby('timestamp')['likes'].sum(), use_container_width=True, color="#FF4B4B")
                with c3:
                    st.metric("💬 累計リプライ数", f"{df['replies'].sum():,} 件")
                    st.bar_chart(df.groupby('timestamp')['replies'].sum(), use_container_width=True, color="#FFB800")
                
                st.divider()
                st.subheader("📅 本日の投稿予定")
                data = get_sheet_data(api["sheet_id"], api["g_json"])
                today_str = datetime.now().strftime('%Y/%m/%d')
                today_list = [r for r in data if r.get('投稿日') == today_str]
                if today_list: st.dataframe(pd.DataFrame(today_list)[['時', '分', '本文']], use_container_width=True)
                else: st.success("本日の待機中の投稿はありません。")

                st.divider()
                st.subheader("🏆 高エンゲージメント トップ5")
                df['total_eng'] = df['likes'] + df['replies']
                top5 = df.sort_values('total_eng', ascending=False).head(5)
                for i, row in top5.iterrows():
                    st.markdown(f"""
                    <div class="ranking-box">
                        <div><span class="ranking-rank">#{list(top5.index).index(i) + 1}</span><span style="color:#9CA3AF; font-size: 14px;">{row['timestamp']}</span></div>
                        <p style="margin: 10px 0; font-weight: 500; line-height: 1.5;">{row['text'][:100]}...</p>
                        <div>
                            <span class="stat-badge">👀 閲覧: {row['views']:,}</span>
                            <span class="stat-badge" style="color:#FF4B4B;">❤️ いいね: {row['likes']:,}</span>
                            <span class="stat-badge" style="color:#FFB800;">💬 コメント: {row['replies']:,}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# ------------------------------------------
# 🛒 2. 商品作成＆予約 (全ジャンル・3ルート)
# ------------------------------------------
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    if not api["gemini"]: st.warning("API設定を先に済ませてください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキングから探す", "🔗 商品URLから作る", "📸 画像/スクショから作る"])

        def draw_ui(key):
            c1, c2, c3 = st.columns(3)
            with c1: gender = st.radio("性別", ["女性", "男性", "指定なし"], key=f"g_{key}")
            with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key=f"a_{key}")
            with c3: kids = st.radio("子供", ["なし", "未就学児", "小学生"], key=f"k_{key}")
            
            c4, c5 = st.columns(2)
            with c4: tone = st.selectbox("トーン", tone_list, key=f"t_{key}")
            with c5: length = st.slider("文字数", 30, 400, 80, key=f"l_{key}")
            
            opts = ["手動入力"] + [t["title"] for t in templates]
            sel = st.selectbox("🧠 テンプレート呼び出し", opts, key=f"tmp_{key}")
            ref = next((t["content"] for t in templates if t["title"] == sel), "") if sel != "手動入力" else ""
            ref_post = st.text_area("🧠 参考にするバズ投稿本文", value=ref, key=f"ra_{key}", height=100)
            custom = st.text_area("✍️ 自由な追加指示", key=f"cp_{key}", height=70)
            return f"{gender}, {','.join(age)}, 子供:{kids}", tone, length, ref_post, custom

        def show_final(key, url, img):
            if key in st.session_state:
                p = st.session_state[key]
                with st.expander(f"確認・編集", expanded=True):
                    mk, rk = f"fm_{key}", f"fr_{key}"
                    if mk not in st.session_state: st.session_state[mk] = p["text"]
                    if rk not in st.session_state: st.session_state[rk] = f"▼ 詳細はこちら\n{url}"
                    
                    final_txt = st.text_area("メイン本文", key=mk, height=150)
                    reply_txt = st.text_area("リプライ文章", key=rk, height=100)
                    use_img = st.checkbox("画像あり", value=True, key=f"img_chk_{key}")
                    
                    c_n, c_s = st.columns(2)
                    if c_n.button("🚀 即時投稿", key=f"btn_n_{key}"):
                        mid = post_to_threads(api["threads"], final_txt, image_url=img if use_img else None)
                        if mid: time.sleep(5); post_to_threads(api["threads"], reply_txt, reply_to_id=mid); st.success("投稿成功！")
                    
                    with c_s:
                        d_v, t_v = st.date_input("予約日", key=f"dv_{key}"), st.time_input("時間", key=f"tv_{key}")
                        if st.button("🗓️ 予約リストに追加", key=f"br_{key}"):
                            row = ["", final_txt, d_v.strftime('%Y/%m/%d'), str(t_v.hour), str(t_v.minute), "pending", "", "", reply_txt, img if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row): st.success("予約登録完了！")

        with tab1:
            genres = {
                "🏆 総合": "0", "👗 レディースファッション": "100371", "👔 メンズファッション": "551177",
                "👠 靴": "558885", "👜 バッグ・ブランド": "216129", "💄 美容・コスメ": "100939",
                "⌚ 腕時計": "558929", "💎 ジュエリー・アクセ": "200162", "🍎 食品": "100227",
                "🍪 スイーツ・お菓子": "551167", "🍹 水・ソフトドリンク": "100316", "🔌 家電": "562631",
                "📸 カメラ・スマホ": "211742", "🛋 インテリア・収納": "100804", "🍳 キッチン・調理器具": "558944",
                "🛁 日用品雑貨": "215783", "🍼 キッズ・ベビー": "100533", "🐱 ペット用品": "101213",
                "⚽ スポーツ・アウトドア": "101070", "⛳ ゴルフ用品": "101077", "🚗 車・バイク用品": "503190",
                "🧸 おもちゃ": "101164", "🎨 ホビー": "101165", "🎮 ゲーム": "101205", "📚 本": "200376"
            }
            sel_g = st.selectbox("ランキングを取得したいジャンルを選択", list(genres.keys()), key="rank_sel_v6")
            if st.button("ランキング取得", key="f_rank_v6"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres[sel_g])
            
            if "items" in st.session_state:
                for i, item in enumerate(st.session_state["items"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        c2.write(f"**{item['itemName'][:60]}...**")
                        if c2.button(f"この商品を選ぶ", key=f"sel_r_{i}_v6"): st.session_state["active_item"] = item
                
                if "active_item" in st.session_state:
                    st.divider(); t_str, tone, length, ref, custom = draw_ui("tab1_v6")
                    if st.button("✨ 1件の文章を生成", key="gen_btn_t1_v6"):
                        # 生成時に編集状態をクリア
                        for k in [f"fm_r1", f"fr_r1"]: 
                            if k in st.session_state: del st.session_state[k]
                        it = st.session_state["active_item"]
                        txt = generate_post_text(it["itemName"], it["itemPrice"], t_str, tone, length, custom, ref, api["gemini"])
                        st.session_state["res1"] = {"text": txt}
                    show_final("res1", st.session_state["active_item"]["itemUrl"], st.session_state["active_item"]["mediumImageUrls"][0]["imageUrl"])

        with tab2:
            url_in = st.text_input("楽天の商品URLを貼り付け", key="url_in_v6")
            if st.button("商品情報を取得", key="f_url_v6"):
                st.session_state["url_info"] = get_item_info_from_url(url_in)
            
            if "url_info" in st.session_state:
                info = st.session_state["url_info"]
                st.image(info["imageUrl"], width=150); st.write(info["itemName"])
                t_str, tone, length, ref, custom = draw_ui("tab2_v6")
                if st.button("✨ 本文を生成", key="gen_btn_t2_v6"):
                    for k in [f"fm_res2", f"fr_res2"]: 
                        if k in st.session_state: del st.session_state[k]
                    txt = generate_post_text(info["itemName"], "", t_str, tone, length, custom, ref, api["gemini"])
                    st.session_state["res2"] = {"text": txt}
                show_final("res2", info["itemUrl"], info["imageUrl"])

        with tab3:
            u_img = st.file_uploader("商品のスクショや画像をアップロード", type=["jpg","png","webp"], key="up_t3_v6")
            hint = st.text_input("補足説明（AIへのヒント）", key="hint_t3_v6")
            t_str, tone, length, ref, custom = draw_ui("tab3_v6")
            if st.button("✨ 画像を解析して生成", key="gen_btn_t3_v6"):
                if u_img:
                    img_obj = Image.open(u_img)
                    for k in [f"fm_res3", f"fr_res3"]: 
                        if k in st.session_state: del st.session_state[k]
                    txt = generate_post_text(hint, "", t_str, tone, length, custom, ref, api["gemini"], image=img_obj)
                    st.session_state["res3"] = {"text": txt}
                else: st.error("画像が必要です")
            show_final("res3", "【URLを手動で入力】", "")

# ------------------------------------------
# 🔍 3. 分析 (週次対比デザイン)
# ------------------------------------------
elif page == "3. 分析":
    st.title("🔍 パフォーマンス分析")
    api = st.session_state["api_keys"]
    if api["threads"]:
        with st.spinner("分析中..."):
            raw = get_threads_engagement(api["threads"])
            if raw:
                df = pd.DataFrame(raw)
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
                today = datetime.now().date()
                start_this = today - timedelta(days=today.weekday())
                start_last = start_this - timedelta(days=7)
                
                this_df = df[df['timestamp'] >= start_this]
                last_df = df[(df['timestamp'] >= start_last) & (df['timestamp'] < start_this)]
                
                c1, c2, c3, c4 = st.columns(4)
                def delta(c, p): return f"{c - p}"
                c1.metric("今週の投稿", f"{len(this_df)} 件", delta(len(this_df), len(last_df)))
                c2.metric("今週の閲覧", f"{this_df['views'].sum():,}", delta(this_df['views'].sum(), last_df['views'].sum()))
                c3.metric("今週のいいね", f"{this_df['likes'].sum():,}", delta(this_df['likes'].sum(), last_df['likes'].sum()))
                c4.metric("今週の返信", f"{this_df['replies'].sum():,}", delta(this_df['replies'].sum(), last_df['replies'].sum()))
                
                st.divider()
                st.dataframe(df.sort_values('views', ascending=False), use_container_width=True)

# ------------------------------------------
# ⚙️ 4. API設定 (管理者モード)
# ------------------------------------------
elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード (Secretsロード)", expanded=True):
        pw = st.text_input("合言葉", type="password", key="apw_v6")
        if st.button("設定を一括読み込み"):
            if pw == st.secrets.get("master_password"):
                st.session_state["api_ri"] = st.secrets.get("rakuten_id", "")
                st.session_state["api_rk"] = st.secrets.get("rakuten_key", "")
                st.session_state["api_ra"] = st.secrets.get("rakuten_aff_id", "")
                st.session_state["api_gk"] = st.secrets.get("gemini_key", "")
                st.session_state["api_tt"] = st.secrets.get("threads_token", "")
                st.session_state["api_si"] = st.secrets.get("sheet_id", "")
                st.session_state["api_gj"] = st.secrets.get("g_json", "")
                st.success("ロード完了！保存をクリックして適用。")
    
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
            st.success("設定を保存しました！")

# ------------------------------------------
# 📝 5. テンプレート管理
# ------------------------------------------
elif page == "5. テンプレート管理":
    st.title("📝 テンプレート管理")
    api = st.session_state["api_keys"]
    if api["sheet_id"]:
        with st.form("tmp_v6"):
            ti = st.text_input("テンプレート名"); co = st.text_area("バズる本文の型", height=150)
            if st.form_submit_button("保存"):
                if save_template(api["sheet_id"], api["g_json"], ti, co): st.success("保存完了！"); time.sleep(1); st.rerun()
        st.divider()
        for t in get_templates(api["sheet_id"], api["g_json"]):
            with st.expander(t["title"]): st.write(t["content"])
