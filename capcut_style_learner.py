import os
import sys
import json
import glob
import time
import requests
from dotenv import load_dotenv

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager

load_dotenv()

FEEDBACK_FILE = r"Z:\AI\EDIT AI\user_feedback.json"

def get_capcut_drafts_dir():
    """Returns the absolute path to CapCut User Projects directory."""
    user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    drafts_dir = os.path.join(user_profile, r"AppData\Local\CapCut\User Data\Projects\com.lveditor.draft")
    return drafts_dir

def find_latest_capcut_project():
    """Finds the most recently modified CapCut project folder."""
    drafts_dir = get_capcut_drafts_dir()
    if not os.path.exists(drafts_dir):
        print(f"Error: CapCut drafts directory not found at: {drafts_dir}")
        return None
        
    projects = []
    for item in os.listdir(drafts_dir):
        full_path = os.path.join(drafts_dir, item)
        if os.path.isdir(full_path) and not item.startswith('.'):
            draft_json = os.path.join(full_path, "draft_content.json")
            if os.path.exists(draft_json):
                projects.append(full_path)
                
    if not projects:
        print(f"No valid CapCut draft projects found in {drafts_dir}")
        return None
        
    # Sort by modification time descending
    projects.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_project = projects[0]
    print(f"Found latest CapCut Project: {os.path.basename(latest_project)} ({time.ctime(os.path.getmtime(latest_project))})")
    return latest_project

def analyze_capcut_style(project_dir):
    """Parses draft_content.json to extract Zoom scale, Silence cut rhythm, and BGM audio volume."""
    draft_json = os.path.join(project_dir, "draft_content.json")
    if not os.path.exists(draft_json):
        return None
        
    try:
        with open(draft_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading draft_content.json: {e}")
        return None
        
    print("\n--- Analyzing CapCut Draft Style ---")
    
    # 1. Analyze Video Scales (Dynamic Zoom)
    video_scales = []
    video_gaps = []
    audio_volumes = []
    
    tracks = data.get("tracks", [])
    for track in tracks:
        track_type = track.get("type")
        segments = track.get("segments", [])
        
        # Sort segments by start time
        sorted_segs = sorted(segments, key=lambda s: s.get("target_timerange", {}).get("start", 0))
        
        if track_type == "video":
            for i, seg in enumerate(sorted_segs):
                clip = seg.get("clip") or {}
                scale = clip.get("scale") or {}
                if "x" in scale:
                    val = scale["x"]
                    if val > 0:
                        video_scales.append(val)
                        
                # Measure gaps between consecutive video cuts
                if i < len(sorted_segs) - 1:
                    t1 = seg.get("target_timerange", {})
                    t2 = sorted_segs[i+1].get("target_timerange", {})
                    end1 = t1.get("start", 0) + t1.get("duration", 0)
                    start2 = t2.get("start", 0)
                    gap_sec = (start2 - end1) / 1000000.0
                    if 0.01 <= gap_sec <= 2.0:
                        video_gaps.append(gap_sec)
                        
        elif track_type == "audio":
            for seg in sorted_segs:
                vol = seg.get("volume")
                if vol is not None:
                    audio_volumes.append(vol)
                    
    # Calculate Dynamic Zoom Level
    learned_zoom = 115 # default
    if video_scales:
        rounded_scales = [round(s, 2) for s in video_scales]
        unique_scales = sorted(list(set(rounded_scales)))
        print(f"Detected Video Scale levels in CapCut: {unique_scales}")
        
        if len(unique_scales) >= 2:
            base_s = unique_scales[0]
            zoom_s = unique_scales[1]
            if base_s > 0:
                ratio = zoom_s / base_s
                calc_zoom = int(round(ratio * 100))
                if 105 <= calc_zoom <= 150:
                    learned_zoom = calc_zoom
                else:
                    learned_zoom = 120 if ratio > 1.1 else 115
        elif len(unique_scales) == 1 and unique_scales[0] > 1.1:
            learned_zoom = int(round(unique_scales[0] * 100)) if unique_scales[0] < 1.5 else 120
            
    # Calculate Silence Cut Rhythm
    learned_silence = 0.3 # default
    if video_gaps:
        avg_gap = sum(video_gaps) / len(video_gaps)
        print(f"Detected Cut Gaps ({len(video_gaps)} cuts) -> Avg: {avg_gap:.3f}s, Min: {min(video_gaps):.3f}s, Max: {max(video_gaps):.3f}s")
        if avg_gap < 0.2:
            learned_silence = 0.2
        elif avg_gap < 0.28:
            learned_silence = 0.25
        else:
            learned_silence = 0.3
            
    # Calculate BGM Audio Volume
    learned_bgm_vol = 0.25 # default
    if audio_volumes:
        bgm_vols = [v for v in audio_volumes if 0.01 < v < 0.9]
        if bgm_vols:
            learned_bgm_vol = round(sum(bgm_vols) / len(bgm_vols), 2)
            print(f"Detected Background Music Volumes: {bgm_vols} -> Learned BGM Vol: {learned_bgm_vol}")
            
    style_info = {
        "zoom_percentage": learned_zoom,
        "silence_threshold": learned_silence,
        "bgm_volume": learned_bgm_vol,
        "learned_from_project": os.path.basename(project_dir),
        "learned_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    print("\n=======================================================")
    print("🎯 CapCut Style Extraction Summary:")
    print(f"• Learned Zoom Scale: {learned_zoom}%")
    print(f"• Learned Silence Cut Rhythm: {learned_silence}s")
    print(f"• Learned BGM Volume: {learned_bgm_vol} ({int(learned_bgm_vol * 100)}%)")
    print(f"• Source Draft Project: '{os.path.basename(project_dir)}'")
    print("=======================================================\n")
    
    return style_info

def update_system_style(style_info):
    """Updates user_feedback.json and syncs with Render Cloud Webhook."""
    if not style_info:
        return False
        
    feedback = line_bot_manager.load_user_feedback()
    feedback["zoom_percentage"] = style_info["zoom_percentage"]
    feedback["silence_threshold"] = style_info["silence_threshold"]
    feedback["bgm_volume"] = style_info["bgm_volume"]
    feedback["capcut_learned_project"] = style_info["learned_from_project"]
    feedback["capcut_learned_timestamp"] = style_info["learned_timestamp"]
    
    line_bot_manager.save_user_feedback(feedback)
    print("Updated local user_feedback.json with learned CapCut style parameters.")
    
    # Sync with Render Cloud if configured
    render_url = os.getenv("RENDER_WEBHOOK_URL", "").rstrip('/')
    if render_url:
        try:
            res = requests.post(f"{render_url}/api/feedback", json=feedback, timeout=10)
            if res.status_code == 200:
                print(f"Synced learned style to Render Cloud ({render_url})!")
        except Exception as e:
            print(f"Cloud sync error: {e}")
            
    return True

def run_capcut_style_learner():
    """Scans CapCut drafts, extracts editing style, and updates auto-cutter settings."""
    project_dir = find_latest_capcut_project()
    if not project_dir:
        return False
        
    style_info = analyze_capcut_style(project_dir)
    if style_info:
        update_system_style(style_info)
        return True
    return False

if __name__ == "__main__":
    run_capcut_style_learner()
