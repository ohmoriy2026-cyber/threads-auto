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
# 🎨 デザイナー設計：モダンUI & メニュー非表示
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
    subject = f"「{item_name}」({price}円)" if item_name else "添付画像の商品"
    prompt = f"""{subject}をターゲット【{target_str}】に向けて、{tone}なテイストで約{length}文字で紹介してください。
【絶対条件】
・本文のみを出力すること。
・画像がある場合は、その中身（デザイン、雰囲気、テキスト）を文章に反映させてください。
"""
    if reference_post: prompt += f"\n\n【参考にする投稿】\n{reference_post}"
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

page = st.sidebar.radio("メニュー", ["1. ダッシュボード", "2. 商品作成＆予約", "3. 分析", "4. API設定", "5. テンプレート管理"])

tone_list = ["エモい", "役立つ", "元気", "親近感", "本音レビュー風", "あざと可愛い"]

# ------------------------------------------
# 🛒 2. 商品作成＆予約
# ------------------------------------------
if page == "2. 商品作成＆予約":
    st.title("🛒 商品作成 ＆ 予約")
    api = st.session_state["api_keys"]
    
    if not api["gemini"]: st.warning("API設定を先に済ませてください。")
    else:
        templates = get_templates(api["sheet_id"], api["g_json"])
        tab1, tab2, tab3 = st.tabs(["🏆 ランキング", "🔗 URLから", "📸 画像/スクショから"])

        # 共通入力UI関数 (各タブでキーがぶつからないよう suffix をつける)
        def draw_settings(suffix):
            c1, c2 = st.columns(2)
            with c1: 
                gender = st.radio("性別", ["女性", "男性", "指定なし"], key=f"gen_{suffix}")
                age = st.multiselect("年代", ["10代", "20代", "30代", "40代"], default=["20代"], key=f"age_{suffix}")
            with c2:
                tone = st.selectbox("トーン", tone_list, key=f"tone_{suffix}")
                length = st.slider("文字数", 20, 300, 70, key=f"len_{suffix}")
            
            temp_opt = ["手動入力"] + [t["title"] for t in templates]
            sel_temp = st.selectbox("🧠 テンプレート", temp_opt, key=f"temp_{suffix}")
            ref = next((t["content"] for t in templates if t["title"] == sel_temp), "") if sel_temp != "手動入力" else ""
            ref_post = st.text_area("🧠 参考投稿", value=ref, key=f"ref_area_{suffix}")
            custom = st.text_area("✍️ 自由指示", key=f"custom_{suffix}")
            return f"{gender}, {','.join(age)}", tone, length, ref_post, custom

        # 生成結果表示関数
        def show_result(res_key, default_url, default_img):
            if res_key in st.session_state:
                p = st.session_state[res_key]
                with st.container(border=True):
                    m_key, r_key = f"final_m_{res_key}", f"final_r_{res_key}"
                    if m_key not in st.session_state: st.session_state[m_key] = p["text"]
                    if r_key not in st.session_state: st.session_state[r_key] = f"▼ 詳細はこちら\n{default_url}"
                    
                    st.text_area("本文", key=m_key, height=150)
                    st.text_area("リプライ", key=r_key, height=80)
                    if st.button("🚀 今すぐ投稿", key=f"btn_now_{res_key}"):
                        mid = post_to_threads(api["threads"], st.session_state[m_key], image_url=default_img)
                        if mid:
                            time.sleep(5)
                            post_to_threads(api["threads"], st.session_state[r_key], reply_to_id=mid)
                            st.success("成功！")

        with tab1:
            if st.button("ランキング取得", key="btn_get_rank"):
                st.session_state["items"] = get_rakuten_ranking(api["rakuten_id"], api["rakuten_key"], api["rakuten_aff_id"], "0")
            if "items" in st.session_state:
                for i, item in enumerate(st.session_state["items"]):
                    c1, c2 = st.columns([1, 4])
                    c1.image(item["mediumImageUrls"][0]["imageUrl"])
                    if c2.button(f"選ぶ: {item['itemName'][:30]}...", key=f"sel_{i}"):
                        st.session_state["active_item"] = item
                if "active_item" in st.session_state:
                    st.divider()
                    t_str, tone, length, ref, custom = draw_settings("tab1")
                    if st.button("✨ 本文作成", key="gen_btn_tab1"):
                        item = st.session_state["active_item"]
                        txt = generate_post_text(item["itemName"], item["itemPrice"], t_str, tone, length, custom, ref, api["gemini"])
                        st.session_state["res1"] = {"text": txt}
                    show_result("res1", st.session_state.get("active_item", {}).get("itemUrl", ""), st.session_state.get("active_item", {}).get("mediumImageUrls", [{}])[0].get("imageUrl", ""))

        with tab2:
            url_in = st.text_input("楽天URL", key="url_in_tab2")
            if st.button("商品取得", key="btn_get_url"):
                st.session_state["url_info"] = get_item_info_from_url(url_in)
            if "url_info" in st.session_state:
                info = st.session_state["url_info"]
                st.write(f"商品: {info['itemName']}")
                t_str, tone, length, ref, custom = draw_settings("tab2")
                if st.button("✨ 本文作成", key="gen_btn_tab2"):
                    txt = generate_post_text(info["itemName"], "", t_str, tone, length, custom, ref, api["gemini"])
                    st.session_state["res2"] = {"text": txt}
                show_result("res2", info["itemUrl"], info["imageUrl"])

        with tab3:
            u_img = st.file_uploader("スクショ/画像をアップ", type=["jpg","png"], key="img_up_tab3")
            hint = st.text_input("補足説明 (任意)", key="hint_tab3")
            t_str, tone, length, ref, custom = draw_settings("tab3")
            if st.button("✨ 画像から本文作成", key="gen_btn_tab3_unique"):
                if u_img:
                    txt = generate_post_text(hint, "", t_str, tone, length, custom, ref, api["gemini"], image=Image.open(u_img))
                    st.session_state["res3"] = {"text": txt}
                else: st.error("画像をアップしてください")
            show_result("res3", "【URLを貼り付け】", "")

# ------------------------------------------
# その他のページ
# ------------------------------------------
elif page == "5. テンプレート管理":
    st.title("📝 テンプレート管理")
    api = st.session_state["api_keys"]
    if api["sheet_id"]:
        with st.form("temp_form"):
            t_title = st.text_input("タイトル")
            t_content = st.text_area("本文")
            if st.form_submit_button("保存"):
                if save_template(api["sheet_id"], api["g_json"], t_title, t_content):
                    st.success("保存完了！"); time.sleep(1); st.rerun()
        st.divider()
        for t in get_templates(api["sheet_id"], api["g_json"]):
            with st.expander(t["title"]): st.write(t["content"])

elif page == "4. API設定":
    st.title("⚙️ API設定")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        r_id = c1.text_input("楽天ID", key="api_ri", type="password")
        r_key = c1.text_input("楽天Key", key="api_rk", type="password")
        r_aff = c1.text_input("楽天Aff", key="api_ra", type="password")
        g_key = c2.text_input("Gemini API", key="api_gk", type="password")
        t_tok = c2.text_input("Threads Token", key="api_tt", type="password")
        s_id = c2.text_input("Sheet ID", key="api_si")
        g_js = st.text_area("JSON", key="api_gj", height=100)
        if st.button("保存"):
            st.session_state["api_keys"].update({"rakuten_id":r_id, "rakuten_key":r_key, "rakuten_aff_id":r_aff, "gemini":g_key, "threads":t_tok, "sheet_id":s_id, "g_json":g_js})
            st.success("保存しました！")

elif page == "1. ダッシュボード": st.title("📊 ダッシュボード"); st.info("準備中")
elif page == "3. 分析": st.title("🔍 分析"); st.info("準備中")
