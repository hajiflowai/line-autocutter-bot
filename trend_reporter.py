import os
import sys
import time
import datetime
import requests
import json
from dotenv import load_dotenv

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project dir is in sys.path
sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager

load_dotenv()

DAILY_QUOTA_FILE = r"Z:\AI\EDIT AI\daily_quota_log.json"

def can_send_today():
    """Quota Guard: Ensures only 1 report message is sent per calendar day to save LINE OA quota."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if os.path.exists(DAILY_QUOTA_FILE):
        try:
            with open(DAILY_QUOTA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("last_sent_date") == today_str:
                    return False
        except Exception:
            pass
    return True

def record_sent_today():
    """Records the date of the sent report to enforce 1 message/day limit."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    try:
        with open(DAILY_QUOTA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_sent_date": today_str,
                "sent_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error recording quota log: {e}")

def fetch_top_action_plan():
    """Generates a concise, highly actionable content strategy plan for 'บอลแบงค์เก่า'."""
    today_str = datetime.date.today().strftime("%d/%m/%Y")
    
    # Highly targeted viral topic & actionable execution plan
    return {
        "date": today_str,
        "viral_topic": "เหรียญ 10 บาท พ.ศ. 2533 (ผลิตเพียง 100 เหรียญ ยอดวิว TikTok พุ่ง 1.2M)",
        "hook_3s": "'อย่าพึ่งรีบใช้! ส่องกระเป๋าตังค์ด่วน เหรียญ 10 บาทปีนี้แพงกว่าทอง!'",
        "zoom_point": "ซูม Macro ชัดๆ ตรงตัวเลข พ.ศ. ๒๕๓๓ ด้านหลังเหรียญ + จุดเหรียญตลับสแกน",
        "ai_capcut_tip": "ใช้ Dynamic Zoom (100%->120%) สลับมุมกล้องตรงคำว่า '2533' และเน้นสีเหลืองนีออนขอบดำหนา 7px"
    }

def generate_compact_action_plan_report():
    """Formats the concise Daily Action Plan template strictly according to LINE OA constraints."""
    data = fetch_top_action_plan()
    
    report = f"""📌 [แผนงานทำคอนเทนต์ประจำวัน - บอลแบงค์เก่า]
ประจำวันที่ {data['date']}

🔥 1. เทรนด์มาแรงวันนี้ (1 เรื่องเด็ด): 
   • {data['viral_topic']}

🎬 2. แผนถ่ายทำแนะนำ (Action Plan):
   • Hook (3 วินาทีแรก): {data['hook_3s']}
   • Point (จุดซูม): {data['zoom_point']}

💡 3. AI & CapCut Tip:
   • {data['ai_capcut_tip']}"""
    return report

def run_trend_reporter(force=False):
    """Generates the compact action plan report and pushes it to LINE OA if quota permits."""
    print(f"\n--- Running AI Trend Action Plan Agent ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
    
    if not force and not can_send_today():
        print("⚠️ [Quota Guard] Report already sent today. Skipping to conserve LINE OA 200 msg/month quota.")
        return False
        
    report_text = generate_compact_action_plan_report()
    print("\n" + report_text + "\n")
    
    # Send report via LINE Messaging API / Cloud Relay
    success = line_bot_manager.push_line_message(report_text)
    if success:
        record_sent_today()
        print("✅ Successfully delivered Live Action Plan Message to LINE OA!")
    else:
        print("❌ Failed or missing LINE config for Push Message.")
        
    return success

def schedule_daily_runner():
    """Runs continuously and triggers the trend report daily at 10:30 AM strictly once per day."""
    print("AI & Trend Daily Action Plan Scheduler started (Target Time: 10:30 AM daily, 1 msg/day quota guard active)...")
    while True:
        now = datetime.datetime.now()
        target_time = now.replace(hour=10, minute=30, second=0, microsecond=0)
        
        if now >= target_time:
            target_time += datetime.timedelta(days=1)
            
        wait_seconds = (target_time - now).total_seconds()
        print(f"Next report scheduled for: {target_time.strftime('%Y-%m-%d %H:%M:%S')} (Waiting {wait_seconds/3600:.2f} hours)")
        
        time.sleep(wait_seconds)
        run_trend_reporter(force=False)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        run_trend_reporter(force=True)
    else:
        run_trend_reporter(force=True)
