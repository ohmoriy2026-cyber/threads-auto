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

# ==========================================
# 🎨 デザイナー設計：モダン・クリーンUI (白基調)
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* 全体の背景とテキスト */
    .stApp { background-color: #F8F9FA !important; }
    .main { background-color: #F8F9FA !important; color: #333333 !important; font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif; }
    
    /* サイドバー */
    [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E5E7EB; }
    
    /* コンテナ（枠線・影） */
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: #FFFFFF !important; border: 1px solid #E5E7EB !important; 
        border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    
    /* 入力フォーム群 */
    div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"], input, textarea, select {
        background-color: #FFFFFF !important; color: #1F2937 !important; border: 1px solid #D1D5DB !important; border-radius: 8px !important;
    }
    
    /* ボタンデザイン */
    .stButton>button { 
        background-color: #007AFF !important; color: #FFFFFF !important; font-weight: bold; 
        border-radius: 8px; width: 100%; border: none; padding: 0.5rem 1rem; transition: all 0.2s;
    }
    .stButton>button:hover { background-color: #0056b3 !important; transform: translateY(-1px); box-shadow: 0 4px 6px rgba(0,122,255,0.2); }
    
    /* メトリクス（数値）のデザイン */
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; color: #111827 !important; }
    [data-testid="stMetricLabel"] { font-size: 1rem !important; font-weight: 600 !important; color: #6B7280 !important; }
    
    /* テーブルのデザイン */
    [data-testid="stDataFrame"] { background-color: #FFFFFF !important; border-radius: 8px; border: 1px solid #E5E7EB; }
    
    /* トップ5ランキング専用スタイル */
    .ranking-box {
        background-color: #FFFFFF; border-left: 5px solid #007AFF; border-radius: 8px; 
        padding: 15px 20px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border-top: 1px solid #F3F4F6; border-right: 1px solid #F3F4F6; border-bottom: 1px solid #F3F4F6;
    }
    .ranking-rank { font-size: 20px; font-weight: 900; color: #007AFF; margin-right: 10px; }
    .ranking-text { color: #374151; font-size: 15px; line-height: 1.5; margin: 10px 0; font-weight: 500;}
    .stat-badge { display: inline-block; background: #F3F4F6; padding: 4px 10px; border-radius: 20px; font-size: 13px; font-weight: bold; margin-right: 8px; color: #4B5563; }
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
    url = f"https://graph.threads.net/v1.0/me/threads?fields=id,text,like_count,reply_count,views,timestamp,is_reply&limit=100&access_token={token}"
    try:
        res = requests.get(url).json()
        return res.get("data", [])
    except: return []

def get_rakuten_ranking(app_id, access_key, affiliate_id, genre_id):
    if not app_id or not access_key:
        st.error("楽天 App ID または Access Key が設定されていません。")
        return []
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": str(app_id).strip(), "accessKey": str(access_key).strip(), "genreId": str(genre_id).strip()}
    if affiliate_id and str(affiliate_id).strip(): params["affiliateId"] = str(affiliate_id).strip()
    try:
        res = requests.get(url, params=params, headers={"Referer": "https://localhost/"})
        if res.status_code != 200:
            st.error(f"❌ 楽天APIエラー ({res.status_code}): {res.text}")
            return []
        return [item["Item"] for item in res.json().get("Items", [])[:10]]
    except Exception as e:
        st.error(f"❌ 通信エラー: {e}")
        return []

def generate_post_text(item_name, price, target_str, tone, length, api_key, image=None):
    client = genai.Client(api_key=api_key)
    prompt = f"""楽天商品「{item_name}」({price}円)を、ターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介してください。
【条件】
・挨拶や前置きは一切不要、本文のみを出力すること。
・「詳細はこちら」などのURL誘導文は絶対に書かないこと。
・AIが書いたような無難で不自然な表現は避け、まるで友人が興奮して勧めているような、人間味のあるリアルな言葉を使うこと。
・読んだ人が思わず「なにこれ！」「気になる！」とタップしたくなるような、好奇心をくすぐる魅力的なフックを入れること。"""
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
    st.session_state["api_keys"] = {
        "rakuten_id": "", "rakuten_key": "", "rakuten_aff_id": "", 
        "gemini": "", "threads": "", "sheet_id": "", "g_json": ""
    }

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. エンゲージメント分析", "4. API設定"])

# ==========================================
# 📊 1. ダッシュボード
# ==========================================
if page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    api = st.session_state["api_keys"]

    if not api["sheet_id"] or not api["threads"]:
        st.info("💡 API設定でロードを行うと、ここにダッシュボードが表示されます。")
    else:
        # --- 本日の投稿予定 ---
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
        else:
            st.warning("スプレッドシートからデータを取得できませんでした。")

        st.divider()

        # --- 累計データとグラフ ---
        st.subheader("📈 アカウント総合状況 (直近100件)")
        threads_data = get_threads_engagement(api["threads"])
        
        if threads_data:
            df = pd.DataFrame(threads_data)
            
            # 🌟 エラー回避：列が存在しない場合は強制的に0や空の列を作る
            for col in ['like_count', 'reply_count', 'views']:
                if col not in df.columns:
                    df[col] = 0
            if 'text' not in df.columns: df['text'] = ""
            if 'timestamp' not in df.columns: df['timestamp'] = datetime.now().isoformat()
            if 'is_reply' not in df.columns: df['is_reply'] = False

            df['like_count'] = pd.to_numeric(df['like_count'], errors='coerce').fillna(0).astype(int)
            df['reply_count'] = pd.to_numeric(df['reply_count'], errors='coerce').fillna(0).astype(int)
            df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0).astype(int)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            
            # リプライを除外したオリジナル投稿のみで集計
            df_main = df[df['is_reply'] != True]
            df_main = df_main[~df_main['text'].astype(str).str.contains("▼ 詳細はこちら", na=False)]

            total_posts = len(df_main)
            total_likes = df_main['like_count'].sum()
            total_replies = df_main['reply_count'].sum()

            c1, c2, c3 = st.columns(3)
            with c1: 
                st.metric("📝 累計投稿数 (オリジナル)", f"{total_posts} 件")
                post_counts = df_main.groupby('timestamp').size()
                st.bar_chart(post_counts, height=150)
            with c2: 
                st.metric("❤️ 累計いいね数", f"{total_likes:,} 回")
                like_counts = df_main.groupby('timestamp')['like_count'].sum()
                st.line_chart(like_counts, height=150, color="#FF4B4B")
            with c3: 
                st.metric("💬 累計リプライ獲得数", f"{total_replies:,} 件")
                reply_counts = df_main.groupby('timestamp')['reply_count'].sum()
                st.line_chart(reply_counts, height=150, color="#FFB800")

            st.divider()

            # --- 高エンゲージトップ5 ---
            st.subheader("🏆 高エンゲージメント トップ5")
            df_main['total_eng'] = df_main['like_count'] + df_main['reply_count']
            
            if not df_main.empty:
                top5_df = df_main.sort_values(by='total_eng', ascending=False).head(5)
                for i, row in top5_df.iterrows():
                    st.markdown(f"""
                    <div class="ranking-box">
                        <div>
                            <span class="ranking-rank">#{top5_df.index.get_loc(i) + 1}</span>
                            <span style="color:#9CA3AF; font-size: 14px;">{row['timestamp']}</span>
                        </div>
                        <p class="ranking-text">{row['text'] if row['text'] else '[画像のみ]'}</p>
                        <div>
                            <span class="stat-badge">👀 閲覧: {row['views']:,}</span>
                            <span class="stat-badge">❤️ いいね: {row['like_count']:,}</span>
                            <span class="stat-badge">💬 コメント: {row['reply_count']:,}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("データがありません。")
        else:
            st.info("Threadsからデータを取得できませんでした。")


# ==========================================
# 🔍 3. エンゲージメント分析 (新設ページ)
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
            
            # 🌟 エラー回避：列が存在しない場合は強制的に0や空の列を作る
            for col in ['like_count', 'reply_count', 'views']:
                if col not in df.columns:
                    df[col] = 0
            if 'text' not in df.columns: df['text'] = ""
            if 'timestamp' not in df.columns: df['timestamp'] = datetime.now().isoformat()
            if 'is_reply' not in df.columns: df['is_reply'] = False

            df['like_count'] = pd.to_numeric(df['like_count'], errors='coerce').fillna(0).astype(int)
            df['reply_count'] = pd.to_numeric(df['reply_count'], errors='coerce').fillna(0).astype(int)
            df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0).astype(int)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            
            # リプライ除外
            df = df[df['is_reply'] != True]
            df = df[~df['text'].astype(str).str.contains("▼ 詳細はこちら", na=False)]

            # --- サマリと先週対比 ---
            st.subheader("📊 今週のパフォーマンス (過去7日間 vs 前週)")
            today = datetime.now().date()
            week_ago = today - timedelta(days=7)
            two_weeks_ago = today - timedelta(days=14)

            # 今週のデータ
            df_this_week = df[(df['timestamp'] > week_ago) & (df['timestamp'] <= today)]
            tw_likes = df_this_week['like_count'].sum()
            tw_views = df_this_week['views'].sum()
            tw_replies = df_this_week['reply_count'].sum()

            # 先週のデータ
            df_last_week = df[(df['timestamp'] > two_weeks_ago) & (df['timestamp'] <= week_ago)]
            lw_likes = df_last_week['like_count'].sum()
            lw_views = df_last_week['views'].sum()
            lw_replies = df_last_week['reply_count'].sum()

            c1, c2, c3 = st.columns(3)
            with c1: st.metric("今週の閲覧数", f"{tw_views:,}", f"{tw_views - lw_views:,} (先週比)")
            with c2: st.metric("今週のいいね", f"{tw_likes:,}", f"{tw_likes - lw_likes:,} (先週比)")
            with c3: st.metric("今週のコメント", f"{tw_replies:,}", f"{tw_replies - lw_replies:,} (先週比)")

            st.divider()

            # --- 全投稿データテーブル ---
            st.subheader("📑 過去の投稿一覧 (全データ)")
            st.write("各項目の見出しをクリックすると並び替えができます。")
            
            display_df = df[['timestamp', 'text', 'views', 'like_count', 'reply_count']].copy()
            display_df.columns = ['投稿日', '投稿内容', '👀 閲覧数', '❤️ いいね', '💬 コメント']
            # 見やすくするために文字数を制限
            display_df['投稿内容'] = display_df['投稿内容'].apply(lambda x: str(x)[:60] + '...' if len(str(x)) > 60 else x)
            
            st.dataframe(display_df.sort_values(by='投稿日', ascending=False), use_container_width=True, hide_index=True)

        else:
            st.info("Threadsデータが取得できませんでした。")


# ==========================================
# 🛒 2. 商品作成＆予約ページ
# ==========================================
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
                target_id = st.text_input("楽天ジャンルIDを入力してください", key="custom_id_in")

            if st.button("ランキング取得", key="get_rank_p2"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], target_id)

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

# ==========================================
# ⚙️ 4. API設定ページ
# ==========================================
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
