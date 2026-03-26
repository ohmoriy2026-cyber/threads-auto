import streamlit as st
import requests
from google import genai
import time
from PIL import Image

# ==========================================
# 🎨 ページ全体の設定とカスタムCSS
# ==========================================
st.set_page_config(page_title="Threads自動投稿ツール", layout="wide")

st.markdown("""
<style>
    .stApp, .main { background-color: #1A1A1D !important; }
    [data-testid="stSidebar"] { background-color: #242429 !important; border-right: 1px solid #3A3A40; }
    [data-testid="stVerticalBlockBorderWrapper"] { background-color: #2A2A30 !important; border: 1px solid #4A4A55 !important; border-radius: 12px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2); }
    .stTextInput div[data-baseweb="input"], .stTextArea div[data-baseweb="textarea"] { background-color: rgba(255, 255, 255, 0.15) !important; border: 1px solid rgba(255, 255, 255, 0.4) !important; border-radius: 8px; }
    .stTextInput input, .stTextArea textarea { color: #FFFFFF !important; }
    .stMarkdown, .stText, h1, h2, h3, p, label { color: #F0F0F0 !important; }
    .stButton>button { background-color: #00E5FF !important; color: #000000 !important; font-weight: bold; border-radius: 8px; border: none; transition: all 0.3s; }
    .stButton>button:hover { background-color: #00B8CC !important; transform: scale(1.02); }
    .stCheckbox label p { color: #00E5FF !important; font-weight: bold; font-size: 1.1em; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 裏側の処理（関数）
# ==========================================
def get_secret(key_name):
    """st.secretsから安全にキーを取得する（未設定時は空文字を返す）"""
    try:
        return st.secrets[key_name]
    except:
        return ""

def get_rakuten_ranking(app_id, access_key, genre_id, limit=10):
    url = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
    params = {"applicationId": app_id, "accessKey": access_key, "genreId": genre_id}
    headers = {"Referer": "https://localhost/"}
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return [item["Item"] for item in response.json().get("Items", [])[:limit]]
        else:
            st.error(f"❌ 楽天APIエラー: {response.text}")
            return []
    except Exception as e:
        st.error(f"❌ 通信エラー: {e}")
        return []

def generate_post_text(item_name, price, target_details, tone, api_key, image=None):
    if not api_key:
        return "⚠️ Gemini APIキーが設定されていません。"
    
    client = genai.Client(api_key=api_key)
    prompt = f"""あなたは優秀なSNSマーケターです。以下の楽天商品を紹介するThreads用の投稿文を作成してください。
【商品】{item_name} / {price}円
【ターゲット】{target_details}
【トーン】{tone}
【条件】
・絵文字を使って親しみやすく短く。最後に「詳細はこちら👇」と入れること。
・【重要】「はい、承知いたしました」などの挨拶、返事、前置きは一切書かず、投稿文の本文のみを出力すること。"""

    if image is not None:
        prompt += "\n・添付された画像も参考にして、商品の魅力を具体的に伝えてください。"
        contents = [prompt, image]
    else:
        contents = prompt

    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=contents)
        return response.text
    except Exception as e:
        return f"❌ AI文章生成エラー: {e}"

def post_to_threads(access_token, text, reply_to_id=None, image_url=None):
    if not access_token:
        st.error("⚠️ Threadsアクセストークンが設定されていません。")
        return None

    create_url = "https://graph.threads.net/v1.0/me/threads"
    
    if image_url:
        create_params = {"access_token": access_token, "media_type": "IMAGE", "image_url": image_url, "text": text}
    else:
        create_params = {"access_token": access_token, "media_type": "TEXT", "text": text}
        
    if reply_to_id:
        create_params["reply_to_id"] = reply_to_id
        
    try:
        create_response = requests.post(create_url, params=create_params)
        if create_response.status_code == 200:
            creation_id = create_response.json().get("id")
            
            if image_url:
                publish_url = f"https://graph.threads.net/v1.0/{creation_id}"
                params = {"access_token": access_token, "fields": "status"}
                for _ in range(6):
                    time.sleep(5)
                    status_check = requests.get(publish_url, params=params).json()
                    if status_check.get("status") == "FINISHED":
                        break
            
            publish_url = "https://graph.threads.net/v1.0/me/threads_publish"
            publish_params = {"access_token": access_token, "creation_id": creation_id}
            publish_response = requests.post(publish_url, params=publish_params)
            
            if publish_response.status_code == 200:
                return publish_response.json().get("id")
            else:
                st.error(f"❌ Threads公開エラー: {publish_response.text}")
        else:
            st.error(f"❌ Threads作成エラー: {create_response.text}")
    except Exception as e:
        st.error(f"❌ 通信エラー: {e}")
    return None

# ==========================================
# 🖥️ メニューとセッション初期化
# ==========================================
st.sidebar.title("📱 メニュー")
page = st.sidebar.radio("ページを選択", ["1. ダッシュボード", "2. 商品ピックアップ＆文章作成", "3. エンゲージメント管理", "4. API設定"])

# セッション状態の初期化
if "api_keys" not in st.session_state:
    st.session_state["api_keys"] = {
        "rakuten_id": get_secret("rakuten_id"),
        "rakuten_key": get_secret("rakuten_key"),
        "gemini": get_secret("gemini_key"),
        "threads": get_secret("threads_token")
    }

# ------------------------------------------
# ページ4: API設定
# ------------------------------------------
if page == "4. API設定":
    st.title("⚙️ API設定")
    st.write("各ツールのAPIキーを入力してください。公開後は st.secrets から自動読み込みされます。")
    
    with st.container(border=True):
        r_id = st.text_input("楽天 アプリケーションID", value=st.session_state["api_keys"]["rakuten_id"], type="password")
        r_key = st.text_input("楽天 アクセスキー", value=st.session_state["api_keys"]["rakuten_key"], type="password")
        g_key = st.text_input("Gemini APIキー", value=st.session_state["api_keys"]["gemini"], type="password")
        t_tok = st.text_input("Threads アクセストークン", value=st.session_state["api_keys"]["threads"], type="password")
        
        if st.button("このAPIキーをセットして使う"):
            st.session_state["api_keys"].update({
                "rakuten_id": r_id, "rakuten_key": r_key, "gemini": g_key, "threads": t_tok
            })
            st.success("✅ APIキーをセットしました！")

# ------------------------------------------
# ページ2: 商品ピックアップ、文章作成
# ------------------------------------------
elif page == "2. 商品ピックアップ＆文章作成":
    st.title("🛒 商品ピックアップ ＆ 📝 文章作成")
    
    api = st.session_state["api_keys"]
    if not api["rakuten_id"]:
        st.warning("⚠️ API設定画面でキーを入力してください。")
    else:
        st.subheader("STEP 1: ジャンルを選んでランキングを取得")
        genres = {
            "総合ランキング": "0", "レディースファッション": "100371", "メンズファッション": "551177", 
            "キッズ・ベビー・マタニティ": "100533", "スイーツ・お菓子": "551167", "食品": "100227",
            "美容・コスメ・香水": "100939", "ダイエット・健康": "100143", "日用品雑貨・文房具・手芸": "215783",
            "インテリア・寝具・収納": "100804", "家電": "211742", "スマートフォン・タブレット": "562637"
        }
        genre_name = st.selectbox("ジャンル", list(genres.keys()))
        
        if st.button("ランキング上位10個をピックアップ"):
            with st.spinner("楽天からデータを取得中..."):
                items = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], genres[genre_name])
                if items:
                    st.session_state["items"] = items
                    if "generated_posts" in st.session_state: del st.session_state["generated_posts"]

        if "items" in st.session_state and st.session_state["items"]:
            st.divider()
            st.subheader("STEP 2: 投稿する商品を選ぶ（複数選択可）")
            items = st.session_state["items"]
            selected_items = []
            
            for i, item in enumerate(items):
                with st.container(border=True):
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        if "mediumImageUrls" in item and len(item["mediumImageUrls"]) > 0:
                            st.image(item["mediumImageUrls"][0]["imageUrl"], use_container_width=True)
                    with col2:
                        st.markdown(f"**【{i+1}位】{item['itemName'][:60]}...**")
                        st.write(f"価格: **{item['itemPrice']}円**")
                        
                        if st.checkbox(f"この商品の文章を作成する", key=f"check_{i}"):
                            uploaded_file = st.file_uploader("📸 画像をアップロード（任意）", type=["jpg", "jpeg", "png"], key=f"upload_{i}")
                            item["uploaded_image"] = uploaded_file
                            selected_items.append(item)
            
            if len(selected_items) > 0:
                st.divider()
                st.subheader("STEP 3: ターゲットとトーンの選択")
                with st.container(border=True):
                    t_col1, t_col2, t_col3 = st.columns(3)
                    with t_col1: gender = st.radio("性別", ["女性", "男性", "指定なし"])
                    with t_col2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代以上"], default=["20代", "30代"])
                    with t_col3: family = st.radio("家族構成", ["指定なし", "未就学児がいる", "小学生がいる"])
                    tone = st.selectbox("文章傾向", ["エモい系", "役立つ系", "共感系", "ハイテンション", "落ち着いた紹介"])
                    
                    if st.button(f"✨ 選んだ {len(selected_items)} 個の文章を一括作成"):
                        target_str = f"性別: {gender}, 年代: {','.join(age)}, 家族構成: {family}"
                        generated_posts = []
                        my_bar = st.progress(0, text="AIが執筆中...")
                        
                        for idx, s_item in enumerate(selected_items):
                            img = None
                            if s_item.get("uploaded_image") is not None:
                                img = Image.open(s_item["uploaded_image"])
                            
                            gen_text = generate_post_text(s_item["itemName"], s_item["itemPrice"], target_str, tone, api["gemini"], img)
                            generated_posts.append({"item": s_item, "text": gen_text})
                            my_bar.progress((idx + 1) / len(selected_items))
                            time.sleep(1)
                            
                        st.session_state["generated_posts"] = generated_posts
                        st.success("完成しました！")

        if "generated_posts" in st.session_state:
            st.divider()
            st.subheader("STEP 4: 編集と投稿")
            for i, post_data in enumerate(st.session_state["generated_posts"]):
                item = post_data["item"]
                with st.expander(f"📝 確認: {item['itemName'][:30]}...", expanded=True):
                    edited_text = st.text_area("文章を編集", value=post_data["text"], height=150, key=f"text_{i}")
                    attach_image = st.checkbox("📸 楽天の画像URLを一緒に投稿する", value=True, key=f"attach_{i}")
                    
                    if st.button(f"🚀 Threadsに投稿", key=f"post_{i}"):
                        with st.spinner("投稿中..."):
                            img_url = item["mediumImageUrls"][0]["imageUrl"] if (attach_image and "mediumImageUrls" in item) else None
                            main_id = post_to_threads(api["threads"], edited_text, image_url=img_url)
                            if main_id:
                                time.sleep(5)
                                link_text = f"▼ 詳細はこちら\n{item['itemUrl']}"
                                if post_to_threads(api["threads"], link_text, reply_to_id=main_id):
                                    st.success("🎉 投稿完了！")
                                    st.balloons()
                            else:
                                st.error("❌ メイン投稿に失敗しました。")

# (ダッシュボード等は省略)
elif page == "1. ダッシュボード": st.title("📊 ダッシュボード")
elif page == "3. エンゲージメント管理": st.title("📈 エンゲージメント管理")