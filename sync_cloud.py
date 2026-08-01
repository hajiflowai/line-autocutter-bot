import os
import sys
import time
import json
import requests
from dotenv import load_dotenv

# Ensure project dir is in sys.path
sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager
import auto_cutter

load_dotenv()

RENDER_URL = os.getenv("RENDER_WEBHOOK_URL", "").rstrip('/')

def check_and_sync_cloud():
    """Polls Render.com Cloud Webhook for pending tasks & updated parameters."""
    if not RENDER_URL:
        print("Notice: RENDER_WEBHOOK_URL is not set in .env yet. Using local mode.")
        return
        
    print(f"Checking Cloud Queue & Feedback from Render: {RENDER_URL}...")
    
    # 1. Fetch latest editing parameters from Cloud
    try:
        res_fb = requests.get(f"{RENDER_URL}/api/feedback", timeout=10)
        if res_fb.status_code == 200:
            cloud_fb = res_fb.json()
            line_bot_manager.save_user_feedback(cloud_fb)
            print(f"Synced Cloud Feedback parameters -> Silence: {cloud_fb.get('silence_threshold')}s, Zoom: {cloud_fb.get('zoom_percentage')}%")
    except Exception as e:
        print(f"Error fetching Cloud Feedback: {e}")
        
    # 2. Fetch pending tasks queue from Cloud
    try:
        res_q = requests.get(f"{RENDER_URL}/api/queue", timeout=10)
        if res_q.status_code == 200:
            q_data = res_q.json()
            tasks = q_data.get("pending_tasks", [])
            if tasks:
                print(f"Found {len(tasks)} PENDING tasks from LINE Cloud Queue!")
                for task in tasks:
                    print(f"• Executing Queue Task ID {task.get('id')}: '{task.get('command')}'")
                    
                # Clear queue on Cloud
                requests.post(f"{RENDER_URL}/api/queue/clear", timeout=10)
                print("Cleared processed tasks from Cloud Queue.")
                
                # Check for video files to process
                target_video, should_move = auto_cutter.get_target_video_file()
                if target_video:
                    print(f"Found video file {target_video}. Starting AutoCutter execution...")
                    auto_cutter.process_video(target_video, move_to_processed=should_move)
                else:
                    print("No video file found in RW folder to process for this queued command.")
            else:
                print("No pending tasks in Cloud Queue.")
    except Exception as e:
        print(f"Error fetching Cloud Queue: {e}")

if __name__ == "__main__":
    check_and_sync_cloud()
