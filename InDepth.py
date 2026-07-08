import streamlit as st
import pandas as pd
import requests
import base64
import json
from datetime import datetime
import pytz
from openai import OpenAI

# -----------------------------
# Basic setup
# -----------------------------
st.set_page_config(
    page_title="Private Health Consultation",
    page_icon="🛡️",
    layout="wide"
)

BKK = pytz.timezone("Asia/Bangkok")

OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")
GITHUB_BRANCH = st.secrets.get("GITHUB_BRANCH", "main")
GITHUB_CSV_PATH = st.secrets.get("GITHUB_CSV_PATH", "private_health_consult.csv")

client = OpenAI(api_key=OPENAI_API_KEY)


# -----------------------------
# GitHub CSV functions
# -----------------------------
def github_get_file():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    params = {"ref": GITHUB_BRANCH}
    r = requests.get(url, headers=headers, params=params)

    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]

    if r.status_code == 404:
        return None, None

    raise Exception(f"GitHub read error: {r.status_code} {r.text}")


def github_save_csv(df):
    old_content, sha = github_get_file()
    csv_content = df.to_csv(index=False, encoding="utf-8-sig")
    encoded = base64.b64encode(csv_content.encode("utf-8-sig")).decode("utf-8")

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    payload = {
        "message": f"Update private health consult {datetime.now(BKK).isoformat()}",
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }

    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, data=json.dumps(payload))
    if r.status_code not in [200, 201]:
        raise Exception(f"GitHub save error: {r.status_code} {r.text}")


def append_to_github(row):
    old_content, _ = github_get_file()

    if old_content:
        from io import StringIO
        df = pd.read_csv(StringIO(old_content))
    else:
        df = pd.DataFrame()

    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    github_save_csv(df)


# -----------------------------
# GPT risk analysis
# -----------------------------
def analyze_with_gpt(data):
    system_prompt = """
คุณเป็นระบบช่วยคัดกรองเบื้องต้นสำหรับสถานพยาบาลมหาวิทยาลัย
เน้นสุขภาพทางเพศ STI ความเสี่ยง PEP/PrEP การตั้งครรภ์ ความรุนแรงทางเพศ สุขภาพจิต
และโรคซับซ้อนที่ต้องการความเป็นส่วนตัว

ให้วิเคราะห์เฉพาะเพื่อผู้ดูแลระบบ ไม่ใช่เพื่อแสดงแก่ผู้ใช้

ให้ตอบเป็น JSON เท่านั้น:
{
  "risk_color": "RED/YELLOW/GREEN",
  "main_concern": "...",
  "reason": "...",
  "recommended_action_for_staff": "...",
  "suggested_timeframe": "ทันที/ภายใน 24 ชั่วโมง/ภายใน 1 สัปดาห์/ให้ข้อมูลทั่วไป"
}

เกณฑ์ RED:
- ถูกล่วงละเมิดทางเพศ
- เสี่ยง HIV ภายใน 72 ชั่วโมง
- มีไข้ ปวดท้องน้อยมาก หนอง แผลอวัยวะเพศ ปัสสาวะแสบมาก
- ตั้งครรภ์หรือสงสัยตั้งครรภ์ร่วมกับอาการเสี่ยง
- suicidal idea หรือความเสี่ยงทำร้ายตนเอง
- ความรุนแรงในความสัมพันธ์

YELLOW:
- มีเพศสัมพันธ์ไม่ป้องกัน
- กังวล STI/ตั้งครรภ์ แต่ไม่มีอาการฉุกเฉิน
- ต้องการ PrEP/คุมกำเนิด
- ปัญหาสุขภาพส่วนตัวที่ควรนัดคุย

GREEN:
- ต้องการข้อมูลทั่วไป
- ไม่มีอาการ ไม่มีเหตุเร่งด่วน
"""

    user_prompt = json.dumps(data, ensure_ascii=False)

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        text = response.choices[0].message.content
        return json.loads(text)

    except Exception as e:
        return {
            "risk_color": "YELLOW",
            "main_concern": "ระบบ AI วิเคราะห์ไม่ได้",
            "reason": str(e),
            "recommended_action_for_staff": "ให้เจ้าหน้าที่ทบทวนข้อมูลด้วยตนเอง",
            "suggested_timeframe": "ภายใน 24 ชั่วโมง"
        }


# -----------------------------
# UI
# -----------------------------
st.title("🛡️ Private Health Consultation: KU KPS Infirmary")
st.caption("พื้นที่ปรึกษาสุขภาพส่วนตัวสำหรับนักศึกษาและบุคลากร")

with st.expander("📌 ข้อตกลง ความยินยอม และการรักษาความลับ", expanded=True):
    st.markdown("""
ข้อมูลที่ท่านกรอกจะใช้เพื่อการคัดกรองและให้คำปรึกษาโดยทีมสุขภาพเท่านั้น  
ข้อมูลจะไม่ถูกเปิดเผยต่อเพื่อน อาจารย์ หรือผู้เกี่ยวข้องอื่นโดยไม่จำเป็น  

อย่างไรก็ตาม หากข้อมูลบ่งชี้ภาวะเร่งด่วน เช่น ความเสี่ยงต่อชีวิต การถูกทำร้าย ความรุนแรง หรือภาวะที่ต้องได้รับการดูแลทันที  
ทีมสุขภาพอาจติดต่อเพื่อความปลอดภัยของท่านตามมาตรฐานวิชาชีพ

การตอบแบบฟอร์มนี้ไม่ได้หมายความว่าท่านต้องเข้ารับการรักษา  
ท่านสามารถใช้ช่องทางนี้เพื่อขอคำแนะนำเบื้องต้น หรือนัดหมายเพื่อพูดคุยเพิ่มเติมได้
""")

consent = st.checkbox("ข้าพเจ้ายินยอมให้สถานพยาบาลใช้ข้อมูลนี้เพื่อการคัดกรองและให้คำปรึกษา")

if not consent:
    st.info("กรุณาอ่านและยืนยันความยินยอมก่อนเริ่มใช้งาน")
    st.stop()


# -----------------------------
# Sidebar
# -----------------------------
menu = st.sidebar.radio(
    "เลือกหัวข้อที่ต้องการปรึกษา",
    [
        "ปรึกษาส่วนตัว",
        "คำถามเกี่ยวกับเพศสัมพันธ์",
        "คัดกรองความเสี่ยง STI",
        "การดูแลสุขภาพที่ซับซ้อนและเป็นส่วนตัว",
        "ขอนัดหมาย"
    ]
)


# -----------------------------
# Basic identity
# -----------------------------
st.subheader("1) ข้อมูลเบื้องต้น")

col1, col2 = st.columns(2)
with col1:
    student_id = st.text_input("เลขประจำตัวนักศึกษา/บุคลากร")
with col2:
    nickname = st.text_input("ชื่อเล่น")

timestamp_bkk = datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"เวลาบันทึกข้อมูล: {timestamp_bkk} น. Asia/Bangkok")


# -----------------------------
# Main form
# -----------------------------
st.subheader("2) แบบประเมินเชิงลึก")

with st.form("private_health_form"):

    concern_type = st.multiselect(
        "เรื่องที่ต้องการปรึกษา",
        [
            "กังวลโรคติดต่อทางเพศสัมพันธ์",
            "มีเพศสัมพันธ์โดยไม่ได้ป้องกัน",
            "ถุงยางแตก/หลุด",
            "กังวลตั้งครรภ์",
            "ต้องการคุมกำเนิด",
            "สนใจ PrEP",
            "กังวลหลังมีเพศสัมพันธ์ไม่เกิน 72 ชั่วโมง",
            "มีอาการผิดปกติ",
            "ปัญหาความสัมพันธ์",
            "ถูกบังคับ/ถูกล่วงละเมิด",
            "สุขภาพจิต/ความเครียด",
            "โรคซับซ้อนที่อยากคุยส่วนตัว",
            "อื่น ๆ"
        ]
    )

    last_sex = st.selectbox(
        "มีเพศสัมพันธ์ครั้งล่าสุดเมื่อใด",
        [
            "ไม่มี/ไม่เกี่ยวข้อง",
            "ภายใน 24 ชั่วโมง",
            "24–72 ชั่วโมง",
            "3–7 วัน",
            "มากกว่า 7 วัน",
            "ไม่แน่ใจ/ไม่ต้องการตอบ"
        ]
    )

    protection = st.selectbox(
        "การป้องกันในครั้งล่าสุด",
        [
            "ไม่ได้มีเพศสัมพันธ์",
            "ใช้ถุงยางตลอดและไม่หลุด/ไม่แตก",
            "ใช้ถุงยางแต่แตก/หลุด",
            "ไม่ได้ใช้ถุงยาง",
            "ไม่แน่ใจ",
            "ไม่ต้องการตอบ"
        ]
    )

    symptoms = st.multiselect(
        "มีอาการใดต่อไปนี้หรือไม่",
        [
            "ไม่มีอาการ",
            "ปัสสาวะแสบขัด",
            "มีหนอง/ตกขาวผิดปกติ",
            "แผลหรือตุ่มบริเวณอวัยวะเพศ",
            "ปวดท้องน้อย",
            "ไข้",
            "ปวดอัณฑะ",
            "คัน/แสบ",
            "เลือดออกผิดปกติ",
            "กังวลมาก นอนไม่หลับ",
            "อื่น ๆ"
        ]
    )

    pregnancy_concern = st.selectbox(
        "มีความกังวลเรื่องตั้งครรภ์หรือไม่",
        ["ไม่มี", "มี", "ไม่แน่ใจ", "ไม่เกี่ยวข้อง", "ไม่ต้องการตอบ"]
    )

    violence = st.selectbox(
        "มีเหตุการณ์ถูกบังคับ ข่มขู่ หรือไม่เต็มใจหรือไม่",
        ["ไม่มี", "มี", "ไม่แน่ใจ", "ไม่ต้องการตอบ"]
    )

    mental_health = st.selectbox(
        "ช่วงนี้มีความคิดทำร้ายตนเอง หรือไม่อยากมีชีวิตอยู่หรือไม่",
        ["ไม่มี", "มี", "ไม่แน่ใจ", "ไม่ต้องการตอบ"]
    )

    free_text = st.text_area(
        "เล่าเพิ่มเติมตามที่สะดวก",
        height=150,
        placeholder="เขียนเฉพาะสิ่งที่ท่านสะดวกเล่า ข้อมูลนี้ใช้เพื่อช่วยคัดกรองและให้คำปรึกษา"
    )

    contact_permission = st.radio(
        "ท่านยินยอมให้สถานพยาบาลติดต่อกลับหรือไม่",
        ["ยินยอม", "ยังไม่ต้องการ", "ขอข้อมูลทั่วไปก่อน"]
    )

    contact_channel = st.text_input(
        "ช่องทางติดต่อกลับ เช่น อีเมล หรือเบอร์โทรศัพท์ หากยินยอม"
    )

    submitted = st.form_submit_button("ส่งข้อมูลเพื่อรับคำแนะนำ")


# -----------------------------
# Submit
# -----------------------------
if submitted:
    if not student_id or not nickname:
        st.error("กรุณากรอกเลขประจำตัวและชื่อเล่น")
        st.stop()

    data = {
        "timestamp_bkk": timestamp_bkk,
        "menu": menu,
        "student_id": student_id,
        "nickname": nickname,
        "concern_type": concern_type,
        "last_sex": last_sex,
        "protection": protection,
        "symptoms": symptoms,
        "pregnancy_concern": pregnancy_concern,
        "violence": violence,
        "mental_health": mental_health,
        "free_text": free_text,
        "contact_permission": contact_permission,
        "contact_channel": contact_channel,
    }

    ai_result = analyze_with_gpt(data)

    row = {
        **data,
        "concern_type": " | ".join(concern_type),
        "symptoms": " | ".join(symptoms),
        "ai_risk_color_hidden": ai_result.get("risk_color", ""),
        "ai_main_concern_hidden": ai_result.get("main_concern", ""),
        "ai_reason_hidden": ai_result.get("reason", ""),
        "ai_recommended_action_hidden": ai_result.get("recommended_action_for_staff", ""),
        "ai_timeframe_hidden": ai_result.get("suggested_timeframe", ""),
    }

    try:
        append_to_github(row)

        st.success("ส่งข้อมูลเรียบร้อยแล้ว")

        st.markdown("""
### คำแนะนำเบื้องต้น

ขอบคุณที่ไว้วางใจติดต่อสถานพยาบาล  
หากเป็นเรื่องสุขภาพส่วนตัว สุขภาพทางเพศ หรือโรคซับซ้อนที่ต้องการความเป็นส่วนตัว  
สถานพยาบาลสามารถรับปรึกษาในวันหยุดนักขัตฤกษ์ทุกวันตามการนัดหมาย

กรุณาอีเมลเพื่อนัดหมายหรือขอคำแนะนำเพิ่มเติมที่  

**ผศ.นพ.กำธร ตันติวิทยาทันต์**  
**E-mail: kamthorn.t@ku.th**

หากมีอาการรุนแรง เช่น ไข้สูง ปวดท้องน้อยมาก แผลรุนแรง หนองมาก ถูกล่วงละเมิดทางเพศ หรือมีความคิดทำร้ายตนเอง  
กรุณาติดต่อสถานพยาบาลหรือหน่วยฉุกเฉินทันที
""")

        with st.expander("สำหรับผู้ดูแลระบบเท่านั้น"):
            password = st.text_input("Admin password", type="password")
            if password == st.secrets.get("ADMIN_PASSWORD", ""):
                st.json(ai_result)
            elif password:
                st.warning("รหัสไม่ถูกต้อง")

    except Exception as e:
        st.error("บันทึกข้อมูลไม่สำเร็จ")
        st.code(str(e))
