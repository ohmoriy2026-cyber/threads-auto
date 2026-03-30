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
# 🎨 デザイナー設計：テーマ対応のモダンUI & 不要メニュー非表示
# ==========================================
st.set_page_config(page_title="Threads Marketing Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* ヘッダー、メニュー、フッターを非表示 */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display: none;}

    .stApp { font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif; }
    [data-testid="stVerticalBlockBorderWrapper"] { 
        border-radius: 12px; padding: 20px; margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .stButton>button { 
        background-color: #007AFF !important; color: #FFFFFF !important; font-weight: bold; 
        border-radius: 8px; width: 100%; border: none; padding: 0.5rem 1rem;
    }
    .ranking-box {
        border-left: 5px solid #007AFF; border-radius: 8px; 
        padding: 15px 20px; margin-bottom: 12px; background-color: rgba(0, 122, 255, 0.05);
        border: 1px solid rgba(128,128,128,0.2);
    }
    .stat-badge { 
        display: inline-block; background: rgba(128,128,128, 0.15); padding: 4px 10px; 
        border-radius: 20px; font-size: 13px; font-weight: bold; margin-right: 8px; 
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
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id).sheet1.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"スプレッドシートエラー: {e}")
        return False

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
        return {"itemName": title[:100], "imageUrl": image, "itemUrl": url, "itemPrice": ""}
    except: return {"itemName": "", "imageUrl": "", "itemUrl": url, "itemPrice": ""}

def generate_post_text(item_name, price, target_str, tone, length, custom_prompt, reference_post, api_key, image=None):
    client = genai.Client(api_key=api_key)
    # 商品名がない場合は画像から判断するようにプロンプトを調整
    subject = f"「{item_name}」({price}円)" if item_name else "添付画像の商品"
    
    prompt = f"""{subject}をターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介してください。

【絶対条件】
・本文のみを出力し、URL誘導文は書かないこと。
・人間味のあるリアルな言葉を使うこと。
・画像がある場合は、その中身（デザイン、雰囲気、テキスト）を最優先で文章に反映させてください。
"""
    if reference_post: prompt += f"\n\n【文体模倣】\n以下の投稿を参考にしてください：\n{reference_post}"
    if custom_prompt: prompt += f"\n\n【特別指示】\n{custom_prompt}"

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

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. エンゲージメント分析", "4. API設定", "5. テンプレート管理"])

# 共通設定用リスト
tone_list = ["エモい", "役立つ", "元気", "親近感 (友だち風)", "本音レビュー風", "専門家 (プロ目線)", "あざと可愛い", "ズボラ・時短命"]

# ------------------------------------------
# 🛒 2. 商品作成＆予約（3つの入り口）
# ------------------------------------------
if page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["gemini"]: st.warning("API設定を先に済ませてください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキングから探す", "🔗 商品URLから作る", "📸 画像/スクショから作る"])

        # --- 共通入力UIを表示する関数 ---
        def input_settings(key_suffix):
            c1, c2, c3 = st.columns(3)
            with c1: gen = st.radio("性別", ["女性", "男性", "指定なし"], key=f"gen_{key_suffix}")
            with c2: age = st.multiselect("年代", ["10代", "20代", "30代", "40代", "50代〜"], default=["20代", "30代"], key=f"age_{key_suffix}")
            with c3: kids = st.radio("子供", ["なし", "未就学児", "小学生"], key=f"kids_{key_suffix}")
            
            c4, c5 = st.columns(2)
            with c4: tone = st.selectbox("トーン", tone_list, key=f"tone_{key_suffix}")
            with c5: length = st.slider("文字数", 10, 500, 70, step=10, key=f"len_{key_suffix}")
            
            temp_opt = ["手動で入力する"] + [t["title"] for t in templates]
            sel_temp = st.selectbox("🧠 テンプレート呼び出し", temp_opt, key=f"temp_{key_suffix}")
            ref = ""
            if sel_temp != "手動で入力する":
                ref = next((t["content"] for t in templates if t["title"] == sel_temp), "")
            ref_post = st.text_area("🧠 参考にするバズ投稿本文", value=ref, key=f"ref_area_{key_suffix}")
            custom = st.text_area("✍️ 自由な追加指示 (例: 安さを強調して)", key=f"custom_{key_suffix}")
            return f"{gen}, 年代:{','.join(age)}, 子供:{kids}", tone, length, ref_post, custom

        # --- 投稿・予約プレビューを表示する関数 ---
        def show_preview(item_data, result_key):
            if result_key in st.session_state:
                p = st.session_state[result_key]
                with st.expander("✨ 生成結果の確認・編集", expanded=True):
                    # 編集を安定させるセッションステート管理
                    m_key = f"final_m_{result_key}"
                    r_key = f"final_r_{result_key}"
                    if m_key not in st.session_state: st.session_state[m_key] = p["text"]
                    if r_key not in st.session_state: st.session_state[r_key] = f"▼ 詳細はこちら\n{p['url']}"
                    
                    final_txt = st.text_area("メイン本文", key=m_key, height=150)
                    reply_txt = st.text_area("リプライ文章", key=r_key, height=100)
                    use_img = st.checkbox("画像を含める", value=True, key=f"img_chk_{result_key}")
                    
                    c_now, c_sch = st.columns(2)
                    if c_now.button("🚀 即時投稿", key=f"now_{result_key}"):
                        mid = post_to_threads(api["threads"], final_txt, image_url=p["img"] if use_img else None)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], reply_txt, reply_to_id=mid)
                            st.success("投稿成功！")
                    
                    with c_sch:
                        d = st.date_input("予約日", key=f"d_{result_key}")
                        t = st.time_input("時間", key=f"t_{result_key}")
                        if st.button("🗓️ 予約追加", key=f"res_{result_key}"):
                            row = ["", final_txt, d.strftime('%Y/%m/%d'), str(t.hour), str(t.minute), "pending", "", "", reply_txt, p["img"] if use_img else ""]
                            if save_to_sheets(api["sheet_id"], api["g_json"], row): st.success("予約完了！")

        # --- タブ1: ランキング ---
        with tab1:
            genres = {"🏆 総合": "0", "💄 美容": "100939", "🍎 食品": "100227", "👗 レディース": "100371"}
            sel_g = st.selectbox("ジャンル", list(genres.keys()))
            if st.button("ランキング取得"):
                st.session_state["rank_items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], genres[sel_g])
            
            if "rank_items" in st.session_state:
                selected_item = None
                for i, item in enumerate(st.session_state["rank_items"]):
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        c1.image(item["mediumImageUrls"][0]["imageUrl"])
                        c2.write(f"**{item['itemName'][:60]}...**")
                        if c2.button("この商品で作成", key=f"pick_{i}"):
                            st.session_state["active_item"] = item
                
                if "active_item" in st.session_state:
                    st.divider()
                    st.subheader("設定")
                    t_str, tone, length, ref, custom = input_settings("tab1")
                    if st.button("✨ 本文を生成", key="gen_tab1"):
                        item = st.session_state["active_item"]
                        txt = generate_post_text(item["itemName"], item["itemPrice"], t_str, tone, length, custom, ref, api["gemini"])
                        st.session_state["res_tab1"] = {"text": txt, "url": item.get("affiliateUrl", item["itemUrl"]), "img": item["mediumImageUrls"][0]["imageUrl"]}
                    show_preview(None, "res_tab1")

        # --- タブ2: 商品URL ---
        with tab2:
            input_url = st.text_input("楽天URLを貼り付け")
            if st.button("情報取得"):
                with st.spinner("取得中..."):
                    st.session_state["url_info"] = get_item_info_from_url(input_url)
            
            if "url_info" in st.session_state:
                info = st.session_state["url_info"]
                st.image(info["imageUrl"], width=150)
                st.write(f"商品: {info['itemName']}")
                t_str, tone, length, ref, custom = input_settings("tab2")
                if st.button("✨ 本文を生成", key="gen_tab2"):
                    txt = generate_post_text(info["itemName"], "", t_str, tone, length, custom, ref, api["gemini"])
                    st.session_state["res_tab2"] = {"text": txt, "url": create_affiliate_url(info["itemUrl"], api["rakuten_aff_id"]), "img": info["imageUrl"]}
                show_preview(None, "res_tab2")

        # --- タブ3: 画像/スクショから自動作成 ---
        with tab3:
            st.info("📸 商品のスクショや写真をアップすると、AIが商品内容を判断して本文を作ります。")
            u_img = st.file_uploader("画像をアップロード", type=["jpg","png","webp"], key="manual_img")
            manual_name = st.text_input("補足説明・商品名 (任意: AIへのヒントになります)", key="manual_name")
            
            t_str, tone, length, ref, custom = input_settings("tab3")
            
            if st.button("✨ 画像から本文を生成", key="gen_tab3"):
                if not u_img: st.error("画像をアップロードしてください。")
                else:
                    img_obj = Image.open(u_img)
                    with st.spinner("AIが画像を解析して執筆中..."):
                        txt = generate_post_text(manual_name, "", t_str, tone, length, custom, ref, api["gemini"], image=img_obj)
                        # 画像はURLがないため空文字。必要に応じて手動でリプライURLを書き換えてもらう運用
                        st.session_state["res_tab3"] = {"text": txt, "url": "【URLをここに貼り付け】", "img": ""}
            
            if "res_tab3" in st.session_state:
                show_preview(None, "res_tab3")

# ------------------------------------------
# その他のページ (ダッシュボード, テンプレート管理, API設定)
# ------------------------------------------
elif page == "5. テンプレート管理":
    st.title("📝 バズ投稿テンプレート管理")
    api = st.session_state["api_keys"]
    if not api["sheet_id"]: st.warning("API設定を先に済ませてください。")
    else:
        with st.container(border=True):
            st.subheader("➕ 新規登録")
            nt = st.text_input("タイトル (例: 子育てママ向けテンプレート)")
            nc = st.text_area("本文 (参考にするバズ投稿の文体をそのまま貼り付け)", height=150)
            if st.button("💾 保存"):
                if save_template(api["sheet_id"], api["g_json"], nt, nc):
                    st.success("保存しました！"); time.sleep(1); st.rerun()
        
        st.divider()
        st.subheader("📚 登録済み一覧")
        temps = get_templates(api["sheet_id"], api["g_json"])
        for t in temps:
            with st.expander(f"📌 {t['title']}"): st.code(t["content"], language=None)

elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.expander("👤 ロード", expanded=True):
        pw = st.text_input("合言葉", type="password")
        if st.button("ロード"):
            if pw == st.secrets.get("master_password"):
                for k, sk in zip(["f_ri","f_rk","f_ra","f_gk","f_tt","f_si","f_gj"], ["rakuten_id","rakuten_key","rakuten_aff_id","gemini_key","threads_token","sheet_id","g_json"]):
                    st.session_state[k] = st.secrets.get(sk, "")
                st.success("ロード完了！保存ボタンを押してください。")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天ID", key="f_ri", type="password")
        r_key = c1.text_input("楽天Key", key="f_rk", type="password")
        r_aff = c1.text_input("楽天Aff", key="f_ra", type="password")
        g_key = c2.text_input("Gemini API", key="f_gk", type="password")
        t_tok = c2.text_input("Threads Token", key="f_tt", type="password")
        s_id = c2.text_input("Sheet ID", key="f_si")
        g_js = st.text_area("JSON", key="f_gj", height=100)
        if st.button("設定を保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "rakuten_aff_id":r_aff, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("保存しました！")

# ダッシュボードと分析は前回のロジックと同様
elif page == "1. ダッシュボード":
    st.title("📊 ダッシュボード")
    st.info("API設定とスプレッドシートの連携が完了すると、ここに予定が表示されます。")

elif page == "3. エンゲージメント分析":
    st.title("🔍 エンゲージメント分析")
    st.info("Threads APIから直近の投稿データを取得します。")
