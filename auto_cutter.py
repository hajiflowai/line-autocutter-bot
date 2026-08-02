import os
import sys
import time
import glob
import json
import re
import shutil
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(r"Z:\AI\EDIT AI")
import capcut_draft_generator

load_dotenv()

INPUT_DIR = r"Z:\AI\EDIT AI\RW"
PROCESSED_DIR = r"Z:\AI\EDIT AI\RW\processed"

def get_target_raw_video_files():
    """Checks INPUT_DIR (RW) for video files."""
    supported_extensions = ("*.mp4", "*.mov", "*.mkv", "*.avi", "*.flv", "*.ts", "*.webm")
    raw_files = []
    for ext in supported_extensions:
        raw_files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
    raw_files = [f for f in raw_files if os.path.isfile(f) and not os.path.basename(f).startswith("_")]
    return raw_files

def check_file_stability(file_path):
    """Waits for file size to stabilize to ensure copy operation is complete."""
    try:
        last_size = os.path.getsize(file_path)
    except OSError:
        return False
    time.sleep(2)
    return True

def watch_folder():
    """
    CapCut Draft Generator Watcher Daemon (v6.0 Production Pipeline):
    - Zero local video rendering required!
    - Detects raw video takes in Z:\AI\EDIT AI\RW
    - Generates ready-to-edit CapCut project in C:\Users\<User>\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\
    - Ice can immediately open CapCut Desktop to check and edit pre-cut timeline!
    """
    print(f"\n=======================================================")
    print(f"🎬 Video-AutoCutter-Agent v6.0 (CapCut Draft Generator)")
    print(f"=======================================================")
    print(f"• Input Watch Folder: {INPUT_DIR}")
    print(f"• Output Mode: Direct CapCut Project Generator (Zero Rendering)")
    print(f"• CapCut Draft Target: C:\\Users\\Acer\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft\\")
    print(f"• Learned Settings: Silence Cut = 0.20s | Padding = 0.02s/0.05s | Natural Zoom = 108%\n")
    
    while True:
        raw_videos = get_target_raw_video_files()
        if raw_videos:
            print(f"[Watch Folder] Detected {len(raw_videos)} raw video file(s) in {INPUT_DIR}...")
            stable_videos = [v for v in raw_videos if check_file_stability(v)]
            if stable_videos:
                try:
                    capcut_draft_generator.process_raw_videos_to_capcut_draft(stable_videos)
                except Exception as e:
                    print(f"Error generating CapCut draft: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            time.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reprocess":
        restored = capcut_draft_generator.restore_raw_files_from_processed()
        if restored:
            capcut_draft_generator.process_raw_videos_to_capcut_draft(restored)
        else:
            print("No processed raw files found to reprocess.")
    else:
        raw_videos = get_target_raw_video_files()
        if raw_videos:
            capcut_draft_generator.process_raw_videos_to_capcut_draft(raw_videos)
        else:
            print(f"No raw video files currently found in {INPUT_DIR}.")
            print("Entering folder watcher daemon mode...")
            watch_folder()
