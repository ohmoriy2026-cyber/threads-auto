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
# 🎨 デザイナー設計：テーマ対応のモダンUI
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
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
    [data-testid="stMetricLabel"] { font-size: 1rem !important; font-weight: 600 !important; }
    .ranking-box {
        border-left: 5px solid #007AFF; border-radius: 8px; 
        padding: 15px 20px; margin-bottom: 12px; background-color: rgba(0, 122, 255, 0.05);
        border-top: 1px solid rgba(128,128,128,0.2); border-right: 1px solid rgba(128,128,128,0.2); border-bottom: 1px solid rgba(128,128,128,0.2);
    }
    .ranking-rank { font-size: 20px; font-weight: 900; color: #007AFF; margin-right: 10px; }
    .ranking-text { font-size: 15px; line-height: 1.5; margin: 10px 0; font-weight: 500;}
    .stat-badge { 
        display: inline-block; background: rgba(128,128,128, 0.15); padding: 4px 10px; 
        border-radius: 20px; font-size: 13px; font-weight: bold; margin-right: 8px; 
    }
    [data-testid="stTabs"] button { font-size: 16px; font-weight: bold; }
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

# 🌟 新機能：スプレッドシートからバズ投稿テンプレートを読み込む
def get_templates(sheet_id, g_json):
    if not sheet_id or not g_json: return []
    try:
        creds_dict = json.loads(g_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        ss = client.open_by_key(sheet_id)
        try:
            ws = ss.worksheet("テンプレート")
        except:
            ws = ss.add_worksheet(title="テンプレート", rows="100", cols="2")
            ws.append_row(["タイトル", "本文"])
        data = ws.get_all_values()
        if len(data) < 2: return []
        return [{"title": row[0], "content": row[1]} for row in data[1:] if len(row) >= 2 and row[0]]
    except Exception:
        return []

# 🌟 新機能：スプレッドシートにバズ投稿テンプレートを保存する
def save_template(sheet_id, g_json, title, content):
    if not sheet_id or not g_json: return False
    try:
        creds_dict = json.loads(g_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        ss = client.open_by_key(sheet_id)
        try:
            ws = ss.worksheet("テンプレート")
        except:
            ws = ss.add_worksheet(title="テンプレート", rows="100", cols="2")
            ws.append_row(["タイトル", "本文"])
        ws.append_row([title, content])
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

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
                data = ins_res.get("data", [])
                metrics = {}
                for d in data:
                    name = d.get('name')
                    values = d.get('values', [])
                    if values and isinstance(values, list):
                        metrics[name] = values[0].get('value', 0)
                
                thread['views'] = metrics.get('views', 0)
                thread['like_count'] = metrics.get('likes', 0)
                thread['reply_count'] = metrics.get('replies', 0)
            except:
                thread['views'] = 0
                thread['like_count'] = 0
                thread['reply_count'] = 0
            return thread

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            enriched_threads = list(executor.map(fetch_insights, threads))
        return enriched_threads
    except Exception as e: 
        return []

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
        return []

def get_item_info_from_url(url):
    default_info = {"itemName": "", "imageUrl": "", "itemUrl": url, "itemPrice": ""}
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        session = requests.Session()
        res = session.get(url, headers=headers, timeout=10, allow_redirects=True)
        res.encoding = res.apparent_encoding
        html = res.text
        
        final_url = res.url
        
        t_m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = t_m.group(1).strip() if t_m else ""
        title = title.replace("【楽天市場】", "").split("：")[0].strip()
        
        i_m = re.search(r'<meta\s+property="og:image"\s+content="(.*?)"', html, re.IGNORECASE)
        image = i_m.group(1) if i_m else ""
        
        if not title:
            return default_info
            
        return {"itemName": title[:100], "imageUrl": image, "itemUrl": final_url, "itemPrice": ""}
    except Exception:
        return default_info

def create_affiliate_url(url, aff_id):
    if not aff_id: return url
    encoded_url = urllib.parse.quote(url, safe='')
    return f"https://hb.afl.rakuten.co.jp/ichiba/{aff_id}/?pc={encoded_url}"

def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    client = genai.Client(api_key=api_key)
    safe_item_name = item_name if item_name else "画像の商品"
    
    prompt = f"""楽天商品「{safe_item_name}」({price}円)を、ターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介してください。

【絶対条件】
・挨拶や前置きは一切不要、本文のみを出力すること。
・「詳細はこちら」などのURL誘導文は絶対に書かないこと。
・AIが書いたような無難な表現は避け、友人が興奮してLINEしてきたような、人間味のあるリアルな言葉を使うこと。
・添付された画像（スクリーンショット等）がある場合は、画像内のテキストや雰囲気も読み取り、商品の魅力として紹介文に必ず活かしてください。

【冒頭のフック指定（超重要）】
文章の最初の1行目は、必ず以下の「フックワード候補」の中から、商品のジャンルやトーンに最も適したものを1つ選び、自然な形で組み込んでスタートしてください。（※｛企業名等｝の部分は商品に合わせてAIが適切に変えてください）

＜フックワード候補＞
・正直ノーマークだった
・私が愛してやまない、
・私推しの、
・｛企業名等｝さんすいませんでした...
・浮気します...
・事件です。
・圧倒的にかわいい！！！
・出産前に知りたかった...
・男の子のママ...聞こえますか...
"""

    if reference_post:
        prompt += f"\n\n【文体の完全模倣（超重要）】\n以下の参考投稿のテンポ、言葉選び、テンション、絵文字の使い方を完全にコピーして、今回の商品の紹介文を作成してください。\n＜参考投稿＞\n{reference_post}"

    if custom_prompt:
        prompt += f"\n\n【特別追加指示（必ず守ること）】\n{custom_prompt}"

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

# 🌟 ここで「5. テンプレート管理」をメニューに追加しています！
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
                preview_list = [{"予定時間": f"{p.get('時','')}:{p.get('分','')}", "本文プレビュー": p.get('本文', '')[:40] + "..."} for p in today_pending]
                st.dataframe(preview_list, use_container_width=True, hide_index=True)
            else:
                st.success("本日の待機中の投稿はありません。")
        else:
            st.warning("スプレッドシートからデータを取得できませんでした。")

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
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
            
            df_main = df[df['is_reply'] != True]
            df_main = df_main[~df_main['text'].astype(str).str.contains("▼ 詳細はこちら", na=False)]

            total_posts = len(df_main)
            total_likes = df_main['like_count'].sum()
            total_replies = df_main['reply_count'].sum()

            c1, c2, c3 = st.columns(3)
            with c1: 
                st.metric("📝 累計投稿数 (オリジナル)", f"{total_posts} 件")
                post_counts = df_main.groupby('timestamp').size()
                st.bar_chart(post_counts, use_container_width=True)
            with c2: 
                st.metric("❤️ 累計いいね数", f"{total_likes:,} 回")
                like_counts = df_main.groupby('timestamp')['like_count'].sum()
                st.bar_chart(like_counts, use_container_width=True, color="#FF4B4B")
            with c3: 
                st.metric("💬 累計リプライ獲得数", f"{total_replies:,} 件")
                reply_counts = df_main.groupby('timestamp')['reply_count'].sum()
                st.bar_chart(reply_counts, use_container_width=True, color="#FFB800")

            st.divider()

            st.subheader("🏆 高エンゲージメント トップ5")
            df_main['total_eng'] = df_main['like_count'] + df_main['reply_count']
            
            if not df_main.empty:
                top5_df = df_main.sort_values(by='total_eng', ascending=False).head(5)
                for i, row in top5_df.iterrows():
                    st.markdown(f"""
                    <div class="ranking-box">
                        <div><span class="ranking-rank">#{top5_df.index.get_loc(i) + 1}</span><span style="color:#9CA3AF; font-size: 14px;">{row['timestamp']}</span></div>
                        <p class="ranking-text">{row['text'] if row['text'] else '[画像のみ]'}</p>
                        <div>
                            <span class="stat-badge">👀 閲覧: {row['views']:,}</span>
                            <span class="stat-badge" style="color:#FF4B4B;">❤️ いいね: {row['like_count']:,}</span>
                            <span class="stat-badge" style="color:#FFB800;">💬 コメント: {row['reply_count']:,}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("データがありません。")
        else:
            st.info("Threadsからデータを取得できませんでした。")


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
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("👀 累計閲覧数", f"{df['views'].sum():,}")
            with c2: st.metric("❤️ 累計いいね数", f"{df['like_count'].sum():,}")
            with c3: st.metric("💬 累計コメント数", f"{df['reply_count'].sum():,}")

            st.divider()

            st.subheader("📑 過去の投稿一覧 (全データ)")
            st.write("各項目の見出しをクリックすると並び替えができます。")
            
            display_df = df[['timestamp', 'text', 'views', 'like_count', 'reply_count']].copy()
            display_df.columns = ['投稿日', '投稿内容', '👀 閲覧数', '❤️ いいね', '💬 コメント']
            display_df['投稿内容'] = display_df['投稿内容'].apply(lambda x: str(x)[:60] + '...' if len(str(x)) > 60 else x)
            
            st.dataframe(display_df.sort_values(by='投稿日', ascending=False), use_container_width=True, hide_index=True)


# ==========================================
# 🛒 2. 商品作成＆予約ページ
# ==========================================
elif page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["rakuten_id"]: 
        st.warning("API設定を先に済ませてください。")
    else:
        tone_list = [
            "エモい", "役立つ", "元気", "親近感 (友だち風)", "本音レビュー風", 
            "専門家 (プロ目線)", "ユーモア (面白く)", "あざと可愛い", "高級感 (エレガント)", "ズボラ・時短命"
        ]
        
        # 🌟 保存済みのテンプレートを取得
        templates = get_templates(api["sheet_id"], api["g_json"])
        template_options = ["手動で入力する"] + [t["title"] for t in templates]

        tab1, tab2 = st.tabs(["🏆 ランキングから探す", "🔗 商品URLから作る"])

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
                
                target_id = genres_dict[sel_name]
                if target_id == "custom":
                    target_id = st.text_input("楽天ジャンルIDを入力してください", key="custom_id_in_p1")

                if st.button("ランキング取得", key="get_rank_p1"):
                    st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], target_id)
                    if "gen_res_p1" in st.session_state: del st.session_state["gen_res_p1"]

            if "items" in st.session_state:
                selected = []
                for i, item in enumerate(st.session_state["items"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        c2.write(f"**{item['itemName'][:50]}...**")
                        if c2.checkbox("選ぶ", key=f"sel_chk_{i}"):
                            item["u_img"] = c2.file_uploader("📸 オリジナル画像や参考スクショをアップロード", type=["jpg","png"], key=f"u_f_{i}")
                            selected.append(item)
                
                if selected:
                    st.divider()
                    with st.container(border=True):
                        st.subheader("ターゲット・文章設定")
                        c1, c2, c3 = st.columns(3)
                        with c1: gender = st.radio("性別", ["女性", "男性", "指定なし"], key="r_gen_p1")
                        with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="m_age_p1")
                        with c3: kids = st.radio("子供", ["なし", "未就学児", "小学生"], key="r_kids_p1")
                        
                        c4, c5 = st.columns(2)
                        with c4: tone = st.selectbox("トーン", tone_list, key="s_tone_p1")
                        with c5: length = st.slider("文字数", 10, 500, 50, step=10, key="s_len_p1")
                        
                        sel_temp_p1 = st.selectbox("🧠 バズ投稿テンプレートを呼び出す", template_options, key="sel_temp_p1")
                        if sel_temp_p1 == "手動で入力する":
                            ref_post_p1 = st.text_area("🧠 参考にするバズ投稿（手動入力）", placeholder="あのバズっている投稿の文章をコピペしてください", key="ref_post_p1")
                        else:
                            selected_content = next((t["content"] for t in templates if t["title"] == sel_temp_p1), "")
                            ref_post_p1 = st.text_area("🧠 呼び出し中のテンプレート（そのまま反映されます）", value=selected_content, key="ref_post_p1_auto")
                            
                        custom_prompt = st.text_area("✍️ 自由な追加指示 (オプション)", placeholder="例: メリットを3つ箇条書きで！", key="c_prompt_p1")
                        
                        if st.button(f"✨ {len(selected)}件の文章を生成", key="gen_btn_p1"):
                            t_str = f"{gender}, 年代:{','.join(age)}, 子供:{kids}"
                            res = []
                            pb = st.progress(0)
                            for j, s_item in enumerate(selected):
                                img_obj = Image.open(s_item["u_img"]) if s_item["u_img"] else None
                                txt = generate_post_text(s_item["itemName"], s_item["itemPrice"], t_str, tone, length, custom_prompt, ref_post_p1, api["gemini"], img_obj)
                                res.append({"item": s_item, "text": txt})
                                pb.progress((j+1)/len(selected))
                            st.session_state["gen_res_p1"] = res

            if "gen_res_p1" in st.session_state:
                for k, p in enumerate(st.session_state["gen_res_p1"]):
                    item = p["item"]
                    target_url = item.get("affiliateUrl", item["itemUrl"])
                    
                    with st.expander(f"確認: {item['itemName'][:30]}", expanded=True):
                        f_txt = st.text_area("メイン本文", value=p["text"], key=f"final_txt_{k}", height=150)
                        
                        st.markdown("**👇 リプライ（ツリー）で投稿する内容**")
                        reply_txt = st.text_area("リプライ文章（アフィリエイトリンク等）", value=f"▼ 詳細はこちら\n{target_url}", key=f"reply_txt_{k}", height=100)
                        
                        use_img = st.checkbox("商品画像を含める", value=True, key=f"use_img_{k}")
                        
                        c_now, c_sch = st.columns(2)
                        if c_now.button("🚀 即時投稿", key=f"btn_now_{k}"):
                            i_url = item["mediumImageUrls"][0]["imageUrl"] if use_img else None
                            mid = post_to_threads(api["threads"], f_txt, image_url=i_url)
                            if mid:
                                time.sleep(5)
                                post_to_threads(api["threads"], reply_txt, reply_to_id=mid)
                                st.success("成功！")
                        
                        with c_sch:
                            d = st.date_input("予約日", key=f"d_in_{k}")
                            t = st.time_input("時間", key=f"t_in_{k}")
                            if st.button("🗓️ 予約リストに追加", key=f"reserve_final_btn_{k}"):
                                row = ["", f_txt, d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", reply_txt, item["mediumImageUrls"][0]["imageUrl"] if use_img else ""]
                                if save_to_sheets(api["sheet_id"], api["g_json"], row):
                                    st.balloons()
                                    st.success(f"✅ 保存しました！ ({d} {t})")

        # ------------------------------------
        # タブ2：商品URLから作る
        # ------------------------------------
        with tab2:
            st.write("楽天の商品ページのURLを直接貼り付けて、自分だけの商品紹介を作ります。")
            with st.container(border=True):
                input_url = st.text_input("🔗 楽天の商品URLを貼り付け", placeholder="https://item.rakuten.co.jp/...", key="input_url_tab2")
                
                if st.button("商品情報を取得", key="get_url_btn_t2"):
                    if input_url:
                        with st.spinner("商品ページから情報を取得しています..."):
                            info = get_item_info_from_url(input_url)
                            if not info["itemName"]:
                                st.warning("⚠️ 楽天のセキュリティにより自動取得がブロックされました。お手数ですが、以下の枠に商品名などを手動で入力してください！")
                            st.session_state["url_item"] = info
                            if "gen_res_tab2" in st.session_state: del st.session_state["gen_res_tab2"]
            
            if "url_item" in st.session_state:
                item = st.session_state["url_item"]
                st.divider()
                st.subheader("📝 商品情報の確認・編集")
                
                c1, c2 = st.columns([1, 4])
                if item["imageUrl"]: c1.image(item["imageUrl"])
                else: c1.info("Web画像なし（ご自身の写真をアップロードしてください）")
                
                edit_name = c2.text_input("商品名（AIに伝わりやすいように編集できます）", value=item["itemName"], key="edit_name_t2")
                edit_price = c2.text_input("価格（任意）", value=item["itemPrice"], key="edit_price_t2")
                
                u_img_tab2 = c2.file_uploader("📸 オリジナル画像や参考スクショをアップロード", type=["jpg","png"], key="u_img_tab2")
                
                st.divider()
                st.subheader("ターゲット・文章設定")
                
                tc1, tc2, tc3 = st.columns(3)
                with tc1: gen_t2 = st.radio("性別", ["女性", "男性", "指定なし"], key="r_gen_t2")
                with tc2: age_t2 = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key="m_age_t2")
                with tc3: kids_t2 = st.radio("子供", ["なし", "未就学児", "小学生"], key="r_kids_t2")
                
                tc4, tc5 = st.columns(2)
                with tc4: tone_t2 = st.selectbox("トーン", tone_list, key="s_tone_t2")
                with tc5: len_t2 = st.slider("文字数", 10, 500, 50, step=10, key="s_len_t2")
                
                sel_temp_t2 = st.selectbox("🧠 バズ投稿テンプレートを呼び出す", template_options, key="sel_temp_t2")
                if sel_temp_t2 == "手動で入力する":
                    ref_post_t2 = st.text_area("🧠 参考にするバズ投稿（手動入力）", placeholder="あのバズっている投稿の文章をコピペしてください", key="ref_post_t2")
                else:
                    selected_content_t2 = next((t["content"] for t in templates if t["title"] == sel_temp_t2), "")
                    ref_post_t2 = st.text_area("🧠 呼び出し中のテンプレート（そのまま反映されます）", value=selected_content_t2, key="ref_post_t2_auto")
                    
                cp_t2 = st.text_area("✍️ 自由な追加指示 (オプション)", key="cp_t2")
                
                if st.button("✨ この商品の文章を生成", key="gen_btn_tab2"):
                    if not edit_name and not u_img_tab2:
                        st.error("商品名を入力するか、画像をアップロードしてください！")
                    else:
                        t_str = f"{gen_t2}, 年代:{','.join(age_t2)}, 子供:{kids_t2}"
                        img_obj_pass = Image.open(u_img_tab2) if u_img_tab2 else None
                        
                        with st.spinner("AIが執筆中..."):
                            txt = generate_post_text(edit_name, edit_price, t_str, tone_t2, len_t2, cp_t2, ref_post_t2, api["gemini"], img_obj_pass)
                            st.session_state["gen_res_tab2"] = {
                                "text": txt,
                                "itemName": edit_name,
                                "target_url": create_affiliate_url(item["itemUrl"], api["rakuten_aff_id"]),
                                "imageUrl": item["imageUrl"]
                            }

            if "gen_res_tab2" in st.session_state:
                p = st.session_state["gen_res_tab2"]
                st.divider()
                st.subheader("✅ 生成結果")
                
                f_txt_t2 = st.text_area("メイン本文", value=p["text"], key="final_txt_t2", height=150)
                
                st.markdown("**👇 リプライ（ツリー）で投稿する内容**")
                reply_txt_t2 = st.text_area("リプライ文章（アフィリエイトリンク等）", value=f"▼ 詳細はこちら\n{p['target_url']}", key="reply_txt_t2", height=100)
                
                use_img_t2 = st.checkbox("商品画像を含める", value=True, key="use_img_t2")
                
                c_now_t2, c_sch_t2 = st.columns(2)
                if c_now_t2.button("🚀 即時投稿", key="btn_now_t2"):
                    i_url = p["imageUrl"] if use_img_t2 else None
                    mid = post_to_threads(api["threads"], f_txt_t2, image_url=i_url)
                    if mid:
                        time.sleep(5)
                        post_to_threads(api["threads"], reply_txt_t2, reply_to_id=mid)
                        st.success("成功！")
                
                with c_sch_t2:
                    d_t2 = st.date_input("予約日", key="d_in_t2")
                    t_t2 = st.time_input("時間", key="t_in_t2")
                    if st.button("🗓️ 予約リストに追加", key="reserve_final_btn_t2"):
                        row = ["", f_txt_t2, d_t2.strftime('%Y/%m/%d'), str(t_t2.hour), str(t_t2.minute), "pending", "", "", reply_txt_t2, p["imageUrl"] if use_img_t2 else ""]
                        if save_to_sheets(api["sheet_id"], api["g_json"], row):
                            st.balloons()
                            st.success(f"✅ 保存しました！ ({d_t2} {t_t2})")

# ==========================================
# 📝 5. テンプレート管理
# ==========================================
elif page == "5. テンプレート管理":
    st.title("📝 バズ投稿テンプレート管理")
    api = st.session_state["api_keys"]
    
    if not api["sheet_id"] or not api["g_json"]:
        st.warning("💡 API設定画面で Sheet ID と JSON を設定すると利用できます。（テンプレートはスプレッドシートに保存されます）")
    else:
        st.write("過去にバズった投稿の文体やテンポを「テンプレート」として保存しておけます。保存したテンプレートは「商品作成」画面でいつでも呼び出してAIに真似させることができます！")
        
        with st.container(border=True):
            st.subheader("➕ 新しいテンプレートを登録")
            new_title = st.text_input("テンプレート名（例：超便利グッズ紹介用、育児の愚痴風 など）")
            new_content = st.text_area("バズ投稿の本文（ここに入れた文章のテンポをAIが真似します）", height=150)
            
            if st.button("💾 テンプレートを保存", key="save_temp_btn"):
                if new_title and new_content:
                    with st.spinner("スプレッドシートに保存しています..."):
                        if save_template(api["sheet_id"], api["g_json"], new_title, new_content):
                            st.success(f"「{new_title}」を保存しました！次回から呼び出せます。")
                            time.sleep(2)
                            st.rerun()
                else:
                    st.error("タイトルと本文の両方を入力してください。")
                    
        st.divider()
        st.subheader("📚 登録済みのテンプレート一覧")
        templates = get_templates(api["sheet_id"], api["g_json"])
        if templates:
            for i, t in enumerate(templates):
                with st.expander(f"📌 {t['title']}"):
                    st.write(t["content"])
        else:
            st.info("まだテンプレートが登録されていません。上のフォームから登録してみましょう！")

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
