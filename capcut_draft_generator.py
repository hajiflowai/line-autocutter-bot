import os
import sys
import time
import uuid
import json
import re
import glob
import shutil
import subprocess
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager

load_dotenv()

CAPCUT_DRAFTS_DIR = r"C:\Users\Acer\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
INPUT_DIR = r"Z:\AI\EDIT AI\RW"
PROCESSED_DIR = r"Z:\AI\EDIT AI\RW\processed"
TRANSCRIPTS_DIR = r"Z:\AI\EDIT AI\transcripts"
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")

def get_transcript_cache(video_path):
    """Gets cached transcript segments if available."""
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    cache_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("segments", [])
        except Exception:
            pass
    return None

def save_transcript_cache(video_path, segments):
    """Saves transcript segments to cache for future instant reuse."""
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    cache_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_video_info(file_path):
    """Retrieves duration, width, and height of the video using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration:format=duration",
        "-of", "json", file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0.0))
        width = int(data["streams"][0]["width"]) if "streams" in data and len(data["streams"]) > 0 else 1080
        height = int(data["streams"][0]["height"]) if "streams" in data and len(data["streams"]) > 0 else 1920
        return duration, width, height
    except Exception as e:
        print(f"Error ffprobe for {file_path}: {e}")
        return 0.0, 1080, 1920

def filter_filler_words_and_stutters(segments):
    """Filters out filler words, stutters, and broken sound fragments."""
    clean_segments = []
    filler_patterns = re.compile(r"^(เอ่อ|อ่า|เออ|อือ|แบบว่า|อั๊วะ|อะ)$", re.IGNORECASE)
    for seg in segments:
        text = seg.get("text", "").strip()
        duration = float(seg.get("end", 0)) - float(seg.get("start", 0))
        if duration < 0.8 and filler_patterns.match(text):
            continue
        clean_segments.append(seg)
    return clean_segments

def get_speech_intervals(segments, total_duration, padding_start=0.02, padding_end=0.05, merge_threshold=0.20):
    """Detects non-silent speech intervals matching CapCut project '0802 (2)' pattern."""
    clean_segs = filter_filler_words_and_stutters(segments)
    raw_intervals = []
    for seg in clean_segs:
        s = max(0.0, float(seg["start"]) - padding_start)
        e = min(total_duration, float(seg["end"]) + padding_end)
        if s < e:
            raw_intervals.append((s, e))
    if not raw_intervals:
        return []
    raw_intervals.sort(key=lambda x: x[0])
    merged = []
    curr_s, curr_e = raw_intervals[0]
    for next_s, next_e in raw_intervals[1:]:
        if next_s - curr_e < merge_threshold:
            curr_e = max(curr_e, next_e)
        else:
            merged.append((curr_s, curr_e))
            curr_s, curr_e = next_s, next_e
    merged.append((curr_s, curr_e))
    return merged

def extract_buddhist_year(segments):
    """Extracts Thai Buddhist Year (พ.ศ. 25XX) from transcription."""
    year_pattern = re.compile(r"(?:พ\.ศ\.|ปี|\b)(25\d{2})\b")
    found_years = []
    for seg in segments:
        text = seg.get("text", "")
        matches = year_pattern.findall(text)
        for m in matches:
            try:
                found_years.append(int(m))
            except ValueError:
                pass
    if found_years:
        return min(found_years)
    return 9999

def create_capcut_draft_project(processed_video_items, project_name=None):
    r"""
    Generates a complete CapCut Draft project folder in C:\Users\<User>\AppData\Local\CapCut\...
    Writes draft_content.json and draft_meta_info.json so CapCut Desktop can open it directly!
    """
    if not project_name:
        project_name = f"AutoCut_{time.strftime('%Y%m%d_%H%M%S')}"
        
    draft_folder_path = os.path.join(CAPCUT_DRAFTS_DIR, project_name)
    os.makedirs(draft_folder_path, exist_ok=True)
    
    print(f"\n=======================================================")
    print(f"🎬 Generating CapCut Draft Project: '{project_name}'")
    print(f"📁 Path: {draft_folder_path}")
    print(f"=======================================================\n")
    
    video_materials = []
    tracks = []
    
    # 1. Main Video Track
    video_track_id = str(uuid.uuid4()).upper()
    video_track = {
        "attribute": 0,
        "flag": 0,
        "id": video_track_id,
        "is_main_track": True,
        "name": "Main Video",
        "segments": [],
        "type": "video"
    }
    
    timeline_target_us = 0
    total_segments_count = 0
    
    for item in processed_video_items:
        vpath = item["path"]
        dur = item["duration"]
        w = item["width"]
        h = item["height"]
        
        dur_us = int(dur * 1000000.0)
        
        mat_id = str(uuid.uuid4()).upper()
        video_material = {
            "id": mat_id,
            "type": "video",
            "duration": dur_us,
            "path": vpath.replace("\\", "/"),
            "has_audio": True,
            "width": w,
            "height": h,
            "category_name": "local",
            "material_name": os.path.basename(vpath),
            "crop_scale": 1.0
        }
        video_materials.append(video_material)
        
        for seg_idx, (start_sec, end_sec) in enumerate(item["intervals"]):
            seg_dur_sec = end_sec - start_sec
            src_start_us = int(start_sec * 1000000.0)
            seg_dur_us = int(seg_dur_sec * 1000000.0)
            
            # Alternating natural zoom (100% vs 108%)
            scale_val = 1.08 if (total_segments_count % 2 == 1) else 1.00
            
            segment_id = str(uuid.uuid4()).upper()
            segment = {
                "id": segment_id,
                "material_id": mat_id,
                "source_timerange": {
                    "start": src_start_us,
                    "duration": seg_dur_us
                },
                "target_timerange": {
                    "start": timeline_target_us,
                    "duration": seg_dur_us
                },
                "render_timerange": {
                    "start": 0,
                    "duration": seg_dur_us
                },
                "clip": {
                    "scale": {"x": scale_val, "y": scale_val},
                    "rotation": 0.0,
                    "transform": {"x": 0.0, "y": 0.0},
                    "flip": {"vertical": False, "horizontal": False},
                    "alpha": 1.0
                },
                "volume": 1.0,
                "speed": 1.0
            }
            
            video_track["segments"].append(segment)
            timeline_target_us += seg_dur_us
            total_segments_count += 1
            
    tracks.append(video_track)
    
    # 2. Build draft_content.json
    draft_content = {
        "canvas_config": {
            "ratio": "9:16",
            "width": 1080,
            "height": 1920
        },
        "duration": timeline_target_us,
        "materials": {
            "videos": video_materials,
            "audios": [],
            "texts": [],
            "stickers": [],
            "effects": []
        },
        "tracks": tracks,
        "version": 6
    }
    
    content_file_path = os.path.join(draft_folder_path, "draft_content.json")
    with open(content_file_path, "w", encoding="utf-8") as f:
        json.dump(draft_content, f, ensure_ascii=False, indent=2)
        
    # 3. Build draft_meta_info.json
    now_us = int(time.time() * 1000000.0)
    draft_meta_info = {
        "draft_id": str(uuid.uuid4()).upper(),
        "draft_name": project_name,
        "draft_fold_path": draft_folder_path.replace("\\", "/"),
        "draft_timeline_materials_size": len(video_materials),
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": timeline_target_us
    }
    
    meta_file_path = os.path.join(draft_folder_path, "draft_meta_info.json")
    with open(meta_file_path, "w", encoding="utf-8") as f:
        json.dump(draft_meta_info, f, ensure_ascii=False, indent=2)
        
    net_duration_sec = timeline_target_us / 1000000.0
    print(f"✅ Successfully created CapCut Draft Project!")
    print(f"   • Name: {project_name}")
    print(f"   • Total Cut Segments on Timeline: {total_segments_count}")
    print(f"   • Total Net Duration: {net_duration_sec:.2f} seconds ({net_duration_sec/60:.2f} mins)")
    print(f"   • Draft Folder: {draft_folder_path}")
    print("👉 Ice can open CapCut Desktop to edit/check the pre-cut timeline immediately!\n")
    
    return draft_folder_path, net_duration_sec

def process_raw_videos_to_capcut_draft(raw_video_paths):
    """Processes raw video files into a CapCut Draft project with zero video rendering!"""
    print(f"Loading Whisper model '{WHISPER_MODEL_NAME}'...")
    import whisper
    model = whisper.load_model(WHISPER_MODEL_NAME)
    
    feedback = line_bot_manager.load_user_feedback()
    silence_thresh = float(feedback.get("silence_threshold", 0.20))
    pad_start = float(feedback.get("padding_start", 0.02))
    pad_end = float(feedback.get("padding_end", 0.05))
    
    processed_items = []
    
    for idx, vpath in enumerate(raw_video_paths):
        print(f"Processing Take {idx+1}/{len(raw_video_paths)}: {os.path.basename(vpath)}...")
        dur, w, h = get_video_info(vpath)
        if dur <= 0:
            continue
            
        segments = get_transcript_cache(vpath)
        if segments is None:
            print("  • Transcribing speech (Whisper STT)...")
            res = model.transcribe(vpath, language="th")
            segments = res.get("segments", [])
            save_transcript_cache(vpath, segments)
            
        buddhist_year = extract_buddhist_year(segments)
        creation_time = os.path.getmtime(vpath)
        speech_intervals = get_speech_intervals(segments, dur, padding_start=pad_start, padding_end=pad_end, merge_threshold=silence_thresh)
        
        if speech_intervals:
            processed_items.append({
                "path": vpath,
                "duration": dur,
                "width": w,
                "height": h,
                "buddhist_year": buddhist_year,
                "creation_time": creation_time,
                "intervals": speech_intervals
            })
            
    if not processed_items:
        print("No processable video files found.")
        return None
        
    # Sort chronologically by พ.ศ. and creation time
    processed_items.sort(key=lambda x: (x["buddhist_year"], x["creation_time"]))
    
    project_name = f"AutoCut_{time.strftime('%Y%m%d_%H%M%S')}"
    draft_path, net_dur = create_capcut_draft_project(processed_items, project_name=project_name)
    
    # Move raw files to processed directory
    for item in processed_items:
        vpath = item["path"]
        if os.path.exists(vpath) and os.path.dirname(os.path.abspath(vpath)) == os.path.abspath(INPUT_DIR):
            dest_path = os.path.join(PROCESSED_DIR, os.path.basename(vpath))
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                shutil.move(vpath, dest_path)
                print(f"📁 Moved raw take file to: {dest_path}")
            except Exception as e:
                print(f"Error moving file: {e}")
                
    # Send report to LINE OA
    line_msg = f"""🎬 [CapCut Draft Created Successfully!]
โปรเจกต์: {project_name}
⏱️ ความยาวตัดเสร็จบนไทม์ไลน์: {net_dur:.2f} วินาที ({net_dur/60:.2f} นาที)
📁 ตำแหน่งโปรเจกต์: {draft_path}

👉 พี่ไอซ์สามารถเปิดแอป CapCut Desktop เข้าไปดูไทม์ไลน์และปรับแต่งต่อได้ทันทีครับ!"""
    line_bot_manager.push_line_message(line_msg)
    
    return draft_path

def restore_raw_files_from_processed():
    """Restores raw files from processed/ back to RW/ for testing."""
    supported = ("*.mp4", "*.mov", "*.mkv", "*.avi")
    restored = []
    for ext in supported:
        for pf in glob.glob(os.path.join(PROCESSED_DIR, ext)):
            dest = os.path.join(INPUT_DIR, os.path.basename(pf))
            try:
                if os.path.exists(dest):
                    os.remove(dest)
                shutil.move(pf, dest)
                restored.append(dest)
            except Exception:
                pass
    return restored

if __name__ == "__main__":
    supported = ("*.mp4", "*.mov", "*.mkv", "*.avi")
    raw_files = []
    for ext in supported:
        raw_files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
        
    if not raw_files:
        print("Restoring raw files from processed for CapCut draft generation test...")
        raw_files = restore_raw_files_from_processed()
        
    if raw_files:
        process_raw_videos_to_capcut_draft(raw_files)
    else:
        print(f"No raw video files found in {INPUT_DIR}.")
