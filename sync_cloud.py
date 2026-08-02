import os
import sys
import time
import json
import requests
from dotenv import load_dotenv

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project dir is in sys.path
sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager
import auto_cutter

load_dotenv()

def check_and_sync_cloud():
    """Polls Render.com Cloud Webhook for pending tasks & updated parameters."""
    render_url = os.getenv("RENDER_WEBHOOK_URL", "").rstrip('/')
    if not render_url:
        print("Notice: RENDER_WEBHOOK_URL is not set in .env yet. Running in local watcher mode.")
        return False
        
    print(f"[{time.strftime('%H:%M:%S')}] Polling Render Cloud: {render_url}...")
    
    # 1. Fetch latest editing parameters from Cloud
    try:
        res_fb = requests.get(f"{render_url}/api/feedback", timeout=10)
        if res_fb.status_code == 200:
            cloud_fb = res_fb.json()
            line_bot_manager.save_user_feedback(cloud_fb)
    except Exception as e:
        print(f"Error fetching Cloud Feedback: {e}")
        
    # 2. Fetch pending tasks queue from Cloud
    try:
        res_q = requests.get(f"{render_url}/api/queue", timeout=10)
        if res_q.status_code == 200:
            q_data = res_q.json()
            tasks = q_data.get("pending_tasks", [])
            if tasks:
                print(f"Found {len(tasks)} PENDING tasks from LINE Cloud Queue!")
                for task in tasks:
                    print(f"  • Task ID {task.get('id')}: '{task.get('command')}'")
                    
                # Clear processed tasks from Cloud Queue
                requests.post(f"{render_url}/api/queue/clear", timeout=10)
                print("Cleared processed tasks from Cloud Queue.")
                return True
    except Exception as e:
        print(f"Error fetching Cloud Queue: {e}")
        
    return False

def start_cloud_worker(interval=10):
    """Continuous background worker for Home PC that syncs with Render Cloud & cuts videos automatically."""
    render_url = os.getenv("RENDER_WEBHOOK_URL", "").rstrip('/')
    print("\n=======================================================")
    print("Home PC Cloud Sync Worker Started!")
    print(f"Render Cloud Endpoint: {render_url if render_url else 'Not Set (Set RENDER_WEBHOOK_URL in .env)'}")
    print(f"Input Watch Directory: {auto_cutter.INPUT_DIR}")
    print(f"Output Directory: {auto_cutter.OUTPUT_DIR}")
    print(f"Polling Interval: {interval} seconds")
    print("=======================================================\n")
    
    while True:
        try:
            # Sync Cloud Queue & Feedback
            has_new_command = check_and_sync_cloud()
            
            # Check if there is a raw video ready to process
            target_video, should_move = auto_cutter.get_target_video_file()
            if target_video:
                if auto_cutter.check_file_stability(target_video):
                    print(f"\nStarting AutoCutter execution for video: {target_video}...")
                    auto_cutter.process_video(target_video, move_to_processed=should_move)
            elif has_new_command:
                print("Received command from LINE, but no raw video file is present in Z:\\AI\\EDIT AI\\RW to process.")
        except Exception as e:
            print(f"Error in Cloud Worker loop: {e}")
            
        time.sleep(interval)

if __name__ == "__main__":
    start_cloud_worker(10)
