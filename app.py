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

# ==========================================
# 🎨 デザイン・カスタムCSS
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide")

st.markdown("""
<style>
    .stApp, .main { background-color: #1A1A1D !important; }
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #26262B !important; border: 1px solid #3A3A40 !important; border-radius: 12px; padding: 20px; margin-bottom: 10px;
    }
    div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"], div[data-baseweb="base-input"],
    input, textarea, select, .stSelectbox div {
        background-color: #000000 !important; color: #FFFFFF !important; border: 1px solid #4A4A55 !important; border-radius: 8px !important;
    }
    div[role="listbox"], div[data-baseweb="popover"], div[data-baseweb="calendar"] {
        background-color: #000000 !important; color: #FFFFFF !important;
    }
    ::placeholder { color: #888888 !important; }
    label, p, h1, h2, h3, .stMarkdown { color: #F0F0F0 !important; font-weight: bold; }
    .stButton>button { background-color: #00E5FF !important; color: #000000 !important; font-weight: bold; border-radius: 8px; width: 100%; border: none; }
    [data-testid="stDataFrame"] { background-color: #000000 !important; border-radius: 8px; }
    
    .ranking-box { background-color: #121214; border: 1px solid #00E5FF; border-radius: 10px; padding: 15px; margin-bottom: 10px; }
    .ranking-rank { font-size: 24px; font-weight: bold; color: #00E5FF; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 関数群
# ==========================================
def save_to_sheets(sheet_id, g_json, row_data):
    if not sheet_id or not g_json: return False
    try:
        creds_dict = json.loads(g_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"スプレッドシートエラー: {e}")
        return False

def get_sheet_data(sheet_id, g_json):
    if not sheet_id or not g_json: return []
    try:
        creds_dict = json.loads(g_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        data = client.open_by_key(sheet_id).sheet1.get_all_values()
        if len(data) < 2: return []
        headers = data[0]
        return [dict(zip(headers, row)) for row in data[1:] if any(row)]
    except: return []

def get_threads_engagement(token):
    if not token: return []
    url = f"https://graph.threads.net/v1.0/me/threads?fields=id,text,like_count,reply_count,views,timestamp&limit=100&access_token={token}"
    try:
        res = requests.get(url).json()
        return res.get("data", [])
    except: return []

# 🌟 エラーが画面に出るように、そして公式最新URLに修正しました
def get_rakuten_ranking(app_id, affiliate_id, genre_id):
    if not app_id:
        st.error("楽天 App ID が設定されていません。API設定を確認してください。")
        return []
        
    url = "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": str(app_id).strip(), "genreId": str(genre_id).strip()}
    if affiliate_id and str(affiliate_id).strip():
        params["affiliateId"] = str(affiliate_id).strip()
        
    try:
        res = requests.get(url, params=params)
        if res.status_code != 200:
            st.error(f"❌ 楽天APIエラー ({res.status_code}): {res.text}")
            return []
        return [item["Item"] for item in res.json().get("Items", [])[:10]]
    except Exception as e:
        st.error(f"❌ 通信エラー: {e}")
        return []

def generate_post_text(item_name, price, target_str, tone, length, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"楽天商品「{item_name}」({price}円)を、ターゲット【{target_str}】に向けて、{tone}な感じで、約{length}文字で作って。挨拶なし、本文のみ。最後に「詳細はこちら👇」必須。"
    contents = [prompt, image] if image else prompt
    return client.models.generate_content(model='gemini-2.5-flash', contents=contents).text

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

# ==========================================
# 🖥️ メイン画面構成
# ==========================================
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {"rakuten_id":"", "rakuten_aff_id":"", "gemini":"", "threads":"", "sheet_id":"", "g_json":""}

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "4. API設定"])

# ------------------------------------------
# 📊 1. ダッシュボードページ
# ------------------------------------------
if page == "1. ダッシュボード":
    st.title("📊 アナリティクス・ダッシュボード")
    api = st.session_state["api_keys"]

    if not api["sheet_id"] or not api["threads"]:
        st.info("💡 API設定でロードを行うと、ここにアナリティクスが表示されます。")
    else:
        st.subheader("❤️ Threads エンゲージメント集計 (過去100件)")
        threads_data = get_threads_engagement(api["threads"])
        
        if threads_data:
            df = pd.DataFrame(threads_data)
            for col in ['like_count', 'reply_count', 'views']:
                if col not in df.columns: df[col] = 0
            if 'text' not in df.columns: df['text'] = ""
            if 'timestamp' not in df.columns: df['timestamp'] = datetime.now().isoformat()

            df['like_count'] = pd.to_numeric(df['like_count'], errors='coerce').fillna(0).astype(int)
            df['reply_count'] = pd.to_numeric(df['reply_count'], errors='coerce').fillna(0).astype(int)
            df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0).astype(int)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            
            total_likes = df['like_count'].sum()
            total_replies = df['reply_count'].sum()
            total_views = df['views'].sum()
            
            ec1, ec2, ec3, ec4 = st.columns(4)
            with ec1: st.metric("📝 対象投稿数", f"{len(threads_data)} 件")
            with ec2: st.metric("👀 累計閲覧数", f"{total_views:,} 回")
            with ec3: st.metric("❤️ 累計いいね数", f"{total_likes:,} 回")
            with ec4: st.metric("💬 累計コメント数", f"{total_replies:,} 件")

            st.divider()

            st.subheader("🏆 反響が大きかった投稿 トップ5")
            df['total_eng'] = df['like_count'] + df['reply_count']
            top5_df = df.sort_values(by='total_eng', ascending=False).head(5)

            for i, row in top5_df.iterrows():
                with st.container():
                    st.markdown(f"""
                    <div class="ranking-box">
                        <span class="ranking-rank">#{top5_df.index.get_loc(i) + 1}</span> &nbsp;&nbsp;
                        <span style="color:#888;">{row['timestamp']}</span><br>
                        <p style="color:#FFF; font-size:16px;">{row['text'][:100] if row['text'] else '[画像のみ/返信]'}</p>
                        <span style="color:#00E5FF;">👀 {row['views']:,}</span> &nbsp;&nbsp;
                        <span style="color:#F0F;">❤️ {row['like_count']}</span> &nbsp;&nbsp;
                        <span style="color:#FF0;">💬 {row['reply_count']}</span>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.divider()

            st.subheader("📈 日別エンゲージメント推移 (いいね + 返信)")
            daily_eng = df.groupby('timestamp')[['like_count', 'reply_count']].sum()
            st.line_chart(daily_eng)

        else:
            st.info("Threadsからデータを取得できませんでした。")

        st.divider()

        st.subheader("⚙️ 自動投稿の待機状況")
        sheet_data = get_sheet_data(api["sheet_id"], api["g_json"])
        if sheet_data:
            pending_items = [r for r in sheet_data if r.get("投稿チェック", "") in ["pending", "予約中", ""]]
            st.metric("⏳ 予約待ち（待機中）", f"{len(pending_items)} 件")
            if pending_items:
                preview_list = []
                for p in pending_items[:5]:
                    dt_str = f"{p.get('投稿日','')} {p.get('時','')}:{p.get('分','')}"
                    txt_prev = p.get('本文', '')[:30] + "..."
                    preview_list.append({"予定日時": dt_str, "本文": txt_prev})
                st.dataframe(preview_list, use_container_width=True)
        else:
            st.warning("スプレッドシートの待機データを取得できませんでした。")

# ------------------------------------------
# 🛒 2. 商品作成＆予約ページ
# ------------------------------------------
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]: st.warning("API設定を先に済ませてください。")
    else:
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
            sel_name = st.selectbox("ランキングを取得したいジャンルを選択", list(genres_dict.keys()), key="sel_genre_p2")
            
            target_id = genres_dict[sel_name]
            if target_id == "custom":
                target_id = st.text_input("楽天ジャンルIDを入力してください（例: 211742）", key="custom_id_in")

            if st.button("ランキング取得", key="get_rank_p2"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_aff_id"], target_id)

        if "items" in st.session_state:
            selected = []
            for i, item in enumerate(st.session_state["items"]):
                with st.container(border=True):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    c2.write(f"**{item['itemName'][:50]}...**")
                    if c2.checkbox("選ぶ", key=f"sel_chk_{i}"):
                        item["u_img"] = c2.file_uploader("画像", type=["jpg","png"], key=f"u_f_{i}")
                        selected.append(item)
            
            if selected:
                st.divider()
                with st.container(border=True):
                    st.subheader("ターゲット・文章設定")
                    c1, c2, c3 = st.columns(3)
                    with c1: gender = st.radio("性別", ["女性", "男性", "指定なし"], key="r_gen")
                    with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="m_age")
                    with c3: kids = st.radio("子供", ["なし", "未就学児", "小学生"], key="r_kids")
                    tone = st.selectbox("トーン", ["エモい", "役立つ", "元気"], key="s_tone")
                    length = st.slider("文字数", 50, 500, 150, step=10, key="s_len")
                    
                    if st.button(f"✨ {len(selected)}件の文章を生成", key="gen_btn_p2"):
                        t_str = f"{gender}, 年代:{','.join(age)}, 子供:{kids}"
                        res = []
                        pb = st.progress(0)
                        for j, s_item in enumerate(selected):
                            img_obj = Image.open(s_item["u_img"]) if s_item["u_img"] else None
                            txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], t_str, tone, length, api["gemini"], img_obj)
                            res.append({"item": s_item, "text": txt})
                            pb.progress((j+1)/len(selected))
                        st.session_state["gen_res_p2"] = res

        if "gen_res_p2" in st.session_state:
            for k, p in enumerate(st.session_state["gen_res_p2"]):
                item = p["item"]
                target_url = item.get("affiliateUrl", item["itemUrl"])
                
                with st.expander(f"確認: {item['itemName'][:30]}", expanded=True):
                    f_txt = st.text_area("本文", value=p["text"], key=f"final_txt_{k}", height=150)
                    use_img = st.checkbox("画像あり", value=True, key=f"use_img_{k}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 即時投稿", key=f"btn_now_{k}"):
                        i_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                        mid = post_to_threads(api["threads"], f_txt, image_url=i_url)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], f"▼ 詳細はこちら\n{target_url}", reply_to_id=mid)
                            st.success("成功！")
                    
                    with c_sch:
                        d = st.date_input("予約日", key=f"d_in_{k}")
                        t = st.time_input("時間", key=f"t_in_{k}")
                        if st.button("🗓️ 予約リストに追加", key=f"reserve_final_btn_{k}"):
                            row = ["", f_txt, d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", f"▼ 詳細はこちら\n{target_url}", item["mediumImageUrls"][0]["imageUrl"] if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                st.balloons()
                                st.success(f"✅ 保存しました！ ({d} {t})")

# ------------------------------------------
# ⚙️ 4. API設定ページ
# ------------------------------------------
elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 管理者モード", expanded=True):
        pw = st.text_input("合言葉", type="password", key="master_pw_input")
        if st.button("ロード", key="load_btn"):
            secret_pw = st.secrets.get("master_password")
            if not secret_pw:
                st.error("❌ Streamlit CloudのSecretsに master_password がありません。")
            elif pw == secret_pw:
                st.session_state["f_ri"] = st.secrets.get("rakuten_id", "")
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
        r_aff = c1.text_input("楽天 アフィリエイトID (任意)", type="password", key="f_ra", help="未入力の場合は通常リンクになります。")
        g_key = c1.text_input("Gemini", type="password", key="f_gk")
        t_tok = c2.text_input("Threads", type="password", key="f_tt")
        s_id = c2.text_input("Sheet ID", key="f_si")
        g_js = c2.text_area("JSON", height=100, key="f_gj")
        
        if st.button("設定を保存", key="f_save_btn"):
            st.session_state["api_keys"].update({
                "rakuten_id":r_id, "rakuten_aff_id":r_aff, "gemini":g_key, 
                "threads":t_tok, "sheet_id":s_id, "g_json":g_js
            })
            st.success("設定を保存しました！商品作成ページへ進んでください。")
