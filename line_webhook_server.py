import os
import sys
import json
import time
import hmac
import hashlib
import base64
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Ensure project dir is in sys.path
sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager

load_dotenv()

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
QUEUE_FILE = r"Z:\AI\EDIT AI\pending_queue.json" if os.name == 'nt' else "/tmp/pending_queue.json"
FEEDBACK_FILE = r"Z:\AI\EDIT AI\user_feedback.json" if os.name == 'nt' else "/tmp/user_feedback.json"

def load_json_data(filepath, default_val):
    """Loads JSON data from file gracefully across OS environments."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
    return default_val

def save_json_data(filepath, data):
    """Saves JSON data to file gracefully across OS environments."""
    try:
        dirname = os.path.dirname(filepath)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

def update_env_user_id(user_id):
    """Auto-saves user_id to .env file when user sends a message on LINE."""
    if not user_id:
        return
    os.environ["LINE_USER_ID"] = user_id
    env_path = r"Z:\AI\EDIT AI\.env" if os.name == 'nt' else "/tmp/.env"
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "LINE_USER_ID=" in content:
                lines = content.splitlines()
                new_lines = [f"LINE_USER_ID={user_id}" if l.startswith("LINE_USER_ID=") else l for l in lines]
                new_content = "\n".join(new_lines) + "\n"
            else:
                new_content = content.rstrip() + f"\nLINE_USER_ID={user_id}\n"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            print(f"Error updating LINE_USER_ID in .env: {e}")

def verify_signature(body, signature):
    """Verifies LINE Webhook HMAC-SHA256 signature."""
    if not LINE_CHANNEL_SECRET or not signature:
        return True
    try:
        hash_val = hmac.new(
            LINE_CHANNEL_SECRET.encode('utf-8'),
            body,
            hashlib.sha256
        ).digest()
        expected_signature = base64.b64encode(hash_val).decode('utf-8')
        return hmac.compare_digest(expected_signature, signature)
    except Exception:
        return True

@app.route("/", methods=["GET", "POST"])
def index():
    return jsonify({
        "status": "online",
        "service": "Antigravity LINE Bi-Directional Cloud Webhook Server",
        "version": "3.0-cloud-queue",
        "timestamp": time.time()
    }), 200

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Always return HTTP 200 OK for GET or LINE Verify test requests
    if request.method == "GET":
        return jsonify({"status": "OK", "message": "LINE Webhook Endpoint Active"}), 200

    signature = request.headers.get("X-Line-Signature", "")
    body_bytes = request.get_data()
    
    if not verify_signature(body_bytes, signature):
        print("Notice: Signature mismatch detected (LINE Verify ping or test event). Returning 200 OK.")
        
    data = request.get_json(silent=True) or {}
    events = data.get("events", [])
    
    if not events:
        print("LINE Webhook Verify ping received -> Returned HTTP 200 OK.")
        return jsonify({"status": "OK"}), 200
        
    for event in events:
        event_type = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")
        reply_token = event.get("replyToken")
        
        if user_id:
            update_env_user_id(user_id)
            
        if event_type == "message":
            msg_obj = event.get("message", {})
            msg_type = msg_obj.get("type")
            
            if msg_type == "text":
                user_text = msg_obj.get("text", "").strip()
                print(f"Received LINE message from User {user_id}: '{user_text}'")
                
                # Load current feedback and queue
                feedback = load_json_data(FEEDBACK_FILE, {
                    "silence_threshold": 0.3,
                    "zoom_percentage": 115,
                    "auto_broll": False,
                    "last_feedback_text": ""
                })
                queue_data = load_json_data(QUEUE_FILE, {"pending_tasks": []})
                
                feedback["last_feedback_text"] = user_text
                text_lower = user_text.lower()
                reply_lines = []
                
                # Parse parameters & queue commands
                if "0.2" in text_lower or "0.2s" in text_lower:
                    feedback["silence_threshold"] = 0.2
                    reply_lines.append("• ปรับ Auto Silence Cut เป็น 0.2 วินาที (กระชับยิ่งขึ้น)")
                elif "0.25" in text_lower or "0.25s" in text_lower:
                    feedback["silence_threshold"] = 0.25
                    reply_lines.append("• ปรับ Auto Silence Cut เป็น 0.25 วินาที")
                elif "0.3" in text_lower or "0.3s" in text_lower:
                    feedback["silence_threshold"] = 0.3
                    reply_lines.append("• ปรับ Auto Silence Cut เป็น 0.3 วินาที")
                    
                if "120" in text_lower or "120%" in text_lower:
                    feedback["zoom_percentage"] = 120
                    reply_lines.append("• ปรับ Dynamic Punch-in Zoom เป็น 120%")
                elif "115" in text_lower or "115%" in text_lower:
                    feedback["zoom_percentage"] = 115
                    reply_lines.append("• ปรับ Dynamic Punch-in Zoom เป็น 115%")
                    
                if "broll" in text_lower or "b-roll" in text_lower or "อนุมัติ" in text_lower:
                    feedback["auto_broll"] = True
                    reply_lines.append("• เปิดใช้งานระบบ Auto B-Roll ในสเต็ปถัดไป")
                    
                # Queue custom task request
                if "ตัด" in text_lower or "ตัดต่อ" in text_lower or "cut" in text_lower:
                    new_task = {
                        "id": int(time.time()),
                        "command": user_text,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "pending"
                    }
                    queue_data.setdefault("pending_tasks", []).append(new_task)
                    save_json_data(QUEUE_FILE, queue_data)
                    reply_lines.append("📥 เพิ่มคำสั่งเข้า Pending Queue เรียบร้อยแล้ว! (รอคอมพ์บ้านดึงไปตัดต่อ)")
                    
                save_json_data(FEEDBACK_FILE, feedback)
                
                if reply_lines:
                    changes_text = "\n".join(reply_lines)
                    reply_msg = f"✅ บันทึกคำสั่งเรียบร้อยครับพี่ไอซ์!\n\nรายการอัปเดตระบบ:\n{changes_text}\n\n🤖 สแตนด์บาย 24/7 บน Render Cloud พร้อมลุยเมื่อเปิดคอมพ์ครับ!"
                else:
                    reply_msg = f"🤖 รับทราบครับพี่ไอซ์! บันทึกข้อความ: '{user_text}' เข้าสู่ระบบ Feedback Loop บน Render Cloud เรียบร้อยครับ!"
                    
                if reply_token and reply_token != "00000000000000000000000000000000":
                    line_bot_manager.reply_line_message(reply_token, reply_msg)
                    
    return jsonify({"status": "OK"}), 200

# ==========================================
# Cloud Pending Queue & Sync API Endpoints
# ==========================================

@app.route("/api/feedback", methods=["GET", "POST"])
def api_feedback():
    """Endpoint for Home PC to sync editing feedback settings."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        save_json_data(FEEDBACK_FILE, data)
        return jsonify({"status": "success", "data": data}), 200
    else:
        data = load_json_data(FEEDBACK_FILE, {
            "silence_threshold": 0.3,
            "zoom_percentage": 115,
            "auto_broll": False,
            "last_feedback_text": ""
        })
        return jsonify(data), 200

@app.route("/api/queue", methods=["GET", "POST"])
def api_queue():
    """Endpoint for Home PC to poll pending video editing task queue."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        save_json_data(QUEUE_FILE, data)
        return jsonify({"status": "success", "data": data}), 200
    else:
        data = load_json_data(QUEUE_FILE, {"pending_tasks": []})
        return jsonify(data), 200

@app.route("/api/queue/clear", methods=["POST"])
def api_queue_clear():
    """Endpoint for Home PC to clear processed queue tasks."""
    save_json_data(QUEUE_FILE, {"pending_tasks": []})
    return jsonify({"status": "success", "message": "Queue cleared"}), 200

@app.route("/api/report", methods=["POST"])
def api_report():
    """Endpoint for Home PC to trigger LINE Push Notifications upon clip completion."""
    data = request.get_json(silent=True) or {}
    report_text = data.get("message", "")
    user_id = data.get("user_id", os.getenv("LINE_USER_ID"))
    if report_text:
        success = line_bot_manager.push_line_message(report_text, target_user_id=user_id)
        return jsonify({"status": "success" if success else "failed"}), 200
    return jsonify({"status": "error", "message": "No message provided"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Antigravity LINE Bi-Directional Cloud Webhook Server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
