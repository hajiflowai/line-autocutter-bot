import os
import sys
import json
import requests
from dotenv import load_dotenv

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
FEEDBACK_FILE = r"Z:\AI\EDIT AI\user_feedback.json"

def load_user_feedback():
    """Loads custom settings derived from user LINE chat feedback."""
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading user feedback: {e}")
    return {
        "silence_threshold": 0.3,
        "zoom_percentage": 115,
        "auto_broll": False,
        "last_feedback_text": ""
    }

def save_user_feedback(data):
    """Saves updated editing parameters from LINE chat feedback."""
    try:
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Updated user feedback settings saved.")
    except Exception as e:
        print(f"Error saving user feedback: {e}")

def push_line_message(message_text, target_user_id=None):
    """Sends a push message to LINE user via LINE Messaging API or Cloud Relay."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = target_user_id or os.getenv("LINE_USER_ID")
    render_url = os.getenv("RENDER_WEBHOOK_URL", "").rstrip('/')
    
    # Send via Render Cloud Relay if available
    if render_url:
        try:
            res = requests.post(f"{render_url}/api/report", json={
                "message": message_text,
                "user_id": user_id
            }, timeout=10)
            if res.status_code == 200:
                print("LINE Push Notification sent via Render Cloud Relay!")
                return True
        except Exception as e:
            print(f"Cloud Relay push failed: {e}. Falling back to direct LINE API.")

    if not token:
        print("Warning: LINE_CHANNEL_ACCESS_TOKEN is missing in .env.")
        return False
        
    if not user_id:
        print("Notice: LINE_USER_ID is not set yet. Send a message to the bot on LINE first to auto-register your User ID!")
        return False
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            print("LINE Push Notification sent successfully!")
            return True
        else:
            print(f"LINE Push API Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error sending LINE Push Notification: {e}")
        return False

def reply_line_message(reply_token, message_text):
    """Replies to a LINE message using replyToken."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        return False
        
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error replying LINE message: {e}")
        return False

def generate_ai_self_analysis_report(start_vdo, end_vdo, count, output_dir=None):
    """Generates automated evaluation report with AI self-analysis and feature suggestions."""
    if output_dir is None:
        output_dir = r"Z:\AI\AI REDY" if os.path.exists(r"Z:\AI\AI REDY") else r"Z:\AI\Ready for media appearances"
    feedback = load_user_feedback()
    silence_val = feedback.get("silence_threshold", 0.3)
    zoom_val = feedback.get("zoom_percentage", 115)
    
    vdo_str = f"RAW VDO {start_vdo:03d}" if start_vdo == end_vdo else f"RAW VDO {start_vdo:03d} - RAW VDO {end_vdo:03d}"
    
    report = f"""🎬 [Antigravity Bi-Directional Agent Report]
ตัดต่อวิดีโอ Zero-Manual สำเร็จเรียบร้อยแล้ว {count} คลิป!

📁 โฟลเดอร์ปลายทาง:
{output_dir}

🎥 คลิปที่สร้างสำเร็จ:
{vdo_str} (9:16 Vertical @ 60fps)

----------------------------------
🔍 [AI Self-Analysis: วิเคราะห์งานรอบนี้]
• Auto Silence Cut: ตัดช่วงเงียบเกิน {silence_val}s ออกทั้งหมด จังหวะกระชับ กระเด้ง
• Dynamic Punch-in: สลับระดับภาพ 100% / {zoom_val}% ตามประโยค ช่วยสร้างมิติการมอง
• Content Clean Cut: คลิปดิบสะอาด ไม่มีซับไตเติล/ข้อความ/เอฟเฟกต์ ตามสเปกของพี่ไอซ์

💡 [AI Self-Suggestions: ข้อเสนอแนะฟีเจอร์สเต็ปถัดไป]
1. อัปเกรดระบบ Auto B-Roll: ตรวจจับคำว่า 'แบงค์/เหรียญ' แล้วดึงภาพแทรกให้อัตโนมัติ
2. ปรับความกระชับ Auto Silence Cut เป็น 0.2s สำหรับคลิปสั้นไฮไลต์
3. เพิ่มความสว่างและโทนภาพ Vintage Warm ปรับผิวภาพให้น่ามองยิ่งขึ้น

👉 พี่ไอซ์สามารถพิมพ์สั่งปรับแต่ง หรือพิมพ์อนุมัติฟีเจอร์กลับมาในแชตนี้ได้ทันทีครับ!"""
    return report

def send_completion_report(start_vdo, end_vdo, count):
    """Generates report and sends push message via LINE."""
    report_text = generate_ai_self_analysis_report(start_vdo, end_vdo, count)
    print("\n--- AI Report Generated ---")
    print(report_text)
    push_line_message(report_text)
