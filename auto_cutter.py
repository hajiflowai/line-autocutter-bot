import os
import sys
import time
import glob
import json
import re
import hashlib
import subprocess
import shutil
import requests
from dotenv import load_dotenv

# Ensure project dir is in sys.path
sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager

# Load environment variables
load_dotenv()

# Configuration
INPUT_DIR = r"Z:\AI\EDIT AI\RW"
OUTPUT_DIR = r"Z:\AI\Ready for media appearances"
PROCESSED_DIR = r"Z:\AI\EDIT AI\RW\processed"
TRANSCRIPTS_DIR = r"Z:\AI\EDIT AI\transcripts"
HISTORY_FILE = r"Z:\AI\EDIT AI\history.json"
PROCESSED_HISTORY_FILE = r"Z:\AI\EDIT AI\processed_history.json"

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny")

# Ensure directories exist
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

def load_history():
    """Loads the history file tracking used timestamps."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading history file: {e}")
    return {}

def save_history(history):
    """Saves the history file tracking used timestamps."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving history file: {e}")

def load_processed_history():
    """Loads the SHA-256 processed history log."""
    if os.path.exists(PROCESSED_HISTORY_FILE):
        try:
            with open(PROCESSED_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading processed history: {e}")
    return {"hashes": {}}

def save_processed_history(data):
    """Saves the SHA-256 processed history log."""
    try:
        with open(PROCESSED_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving processed history: {e}")

def calculate_file_sha256(file_path):
    """Calculates SHA-256 hash of a file for anti-duplication check."""
    print(f"Calculating SHA-256 hash for {os.path.basename(file_path)}...")
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        digest = sha256.hexdigest()
        print(f"SHA-256: {digest}")
        return digest
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None

def is_duplicate_file(file_path):
    """Checks if the video file has already been processed based on SHA-256 hash."""
    file_hash = calculate_file_sha256(file_path)
    if not file_hash:
        return False, None
        
    proc_history = load_processed_history()
    hashes = proc_history.get("hashes", {})
    
    if file_hash in hashes:
        entry = hashes[file_hash]
        print(f"\n[Smart Anti-Duplicate] File '{os.path.basename(file_path)}' SHA-256 matches previously processed video!")
        print(f"  • Processed Timestamp: {entry.get('processed_timestamp')}")
        print(f"  • Previously Created Clips: {entry.get('clips', [])}")
        print("--> Skipping processing to prevent duplicate cuts.\n")
        return True, file_hash
        
    return False, file_hash

def record_processed_file(file_path, file_hash, created_clips):
    """Records successfully processed video file hash and timestamp in history."""
    if not file_hash:
        return
        
    proc_history = load_processed_history()
    hashes = proc_history.setdefault("hashes", {})
    
    now_epoch = time.time()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    hashes[file_hash] = {
        "filename": os.path.basename(file_path),
        "raw_path": file_path,
        "processed_timestamp": now_str,
        "processed_epoch": now_epoch,
        "clips": created_clips
    }
    save_processed_history(proc_history)
    print(f"[Anti-Duplicate] Recorded SHA-256 hash {file_hash[:10]}... into processed_history.json")

def cleanup_old_raw_files(hours_threshold=48):
    """
    Storage Maintenance: Deletes raw video files from INPUT_DIR / PROCESSED_DIR
    that have been successfully processed and are older than hours_threshold (48 hours).
    """
    print(f"\n--- Storage Maintenance Check (Threshold: {hours_threshold} hours) ---")
    proc_history = load_processed_history()
    hashes = proc_history.get("hashes", {})
    
    now_epoch = time.time()
    deleted_count = 0
    
    for file_hash, entry in list(hashes.items()):
        proc_epoch = entry.get("processed_epoch", 0)
        elapsed_hours = (now_epoch - proc_epoch) / 3600.0
        
        if elapsed_hours >= hours_threshold:
            filename = entry.get("filename")
            possible_paths = [
                entry.get("raw_path"),
                os.path.join(INPUT_DIR, filename) if filename else None,
                os.path.join(PROCESSED_DIR, filename) if filename else None
            ]
            
            for path in possible_paths:
                if path and os.path.exists(path) and os.path.isfile(path):
                    try:
                        os.remove(path)
                        deleted_count += 1
                        print(f"🗑️ [Storage Maintenance] Deleted raw file: {path} (processed {elapsed_hours:.1f} hours ago)")
                    except Exception as e:
                        print(f"Error deleting old raw file {path}: {e}")
                        
    print(f"Storage Maintenance finished. Total raw files cleaned up: {deleted_count}\n")

def get_next_raw_vdo_number(output_dir):
    """Scans output_dir for 'RAW VDO XXX.mp4' files and returns the next integer index."""
    pattern = re.compile(r"^RAW\s+VDO\s+(\d+)\.mp4$", re.IGNORECASE)
    max_num = 0
    if os.path.exists(output_dir):
        for fname in os.listdir(output_dir):
            match = pattern.match(fname)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num + 1

def get_transcript_cache(video_path):
    """Gets cached transcript segments if available."""
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    cache_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"Loaded cached transcript from {cache_path}")
                return data.get("segments", [])
        except Exception as e:
            print(f"Error reading transcript cache: {e}")
    return None

def save_transcript_cache(video_path, segments):
    """Saves transcript segments to cache for future instant reuse."""
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    cache_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)
        print(f"Saved transcript cache to {cache_path}")
    except Exception as e:
        print(f"Error saving transcript cache: {e}")

def get_video_info(file_path):
    """Retrieves duration, width, and height of the video using ffprobe."""
    dir_in = os.path.dirname(os.path.abspath(file_path))
    temp_in = os.path.join(dir_in, f"_probe_{os.getpid()}.mp4")
    created_link = False
    try:
        if os.path.exists(temp_in):
            os.remove(temp_in)
        os.link(file_path, temp_in)
        created_link = True
        real_file = temp_in
    except Exception:
        real_file = file_path
        
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration:format=duration",
        "-of", "json", real_file
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(result.stdout)
        
        duration = 0.0
        if "format" in data and "duration" in data["format"]:
            duration = float(data["format"]["duration"])
        elif "streams" in data and len(data["streams"]) > 0 and "duration" in data["streams"][0]:
            duration = float(data["streams"][0]["duration"])
            
        width = int(data["streams"][0]["width"]) if "streams" in data and len(data["streams"]) > 0 else 0
        height = int(data["streams"][0]["height"]) if "streams" in data and len(data["streams"]) > 0 else 0
        
        if created_link and os.path.exists(temp_in):
            try:
                os.remove(temp_in)
            except Exception:
                pass
                
        return duration, width, height
    except Exception as e:
        print(f"Error probe info for {file_path}: {e}")
        if created_link and os.path.exists(temp_in):
            try:
                os.remove(temp_in)
            except Exception:
                pass
        return 0.0, 0, 0

def get_crop_filters(width, height, zoom_percentage=120):
    """
    Generates 100% normal crop and zoom_percentage% punch-in zoom crop filters for vertical 9:16 format (1080x1920).
    """
    target_aspect = 9 / 16
    
    if width <= 0 or height <= 0:
        crop_w, crop_h = 606, 1080
    else:
        input_aspect = width / height
        if input_aspect > target_aspect:
            crop_w = int(height * target_aspect) // 2 * 2
            crop_h = height
        else:
            crop_w = width
            crop_h = int(width / target_aspect) // 2 * 2
            
    filter_100 = f"crop={crop_w}:{crop_h},scale=1080:1920,setsar=1"
    
    zoom_factor = float(zoom_percentage) / 100.0
    zoom_w = int(crop_w / zoom_factor) // 2 * 2
    zoom_h = int(crop_h / zoom_factor) // 2 * 2
    filter_zoom = f"crop={zoom_w}:{zoom_h},scale=1080:1920,setsar=1"
    
    return filter_100, filter_zoom

def filter_filler_words_and_stutters(segments):
    """Filters out filler words, stutters, and broken sound fragments."""
    clean_segments = []
    filler_patterns = re.compile(r"^(เอ่อ|อ่า|เออ|อือ|แบบว่า|อั๊วะ|อะ)$", re.IGNORECASE)
    
    for seg in segments:
        text = seg.get("text", "").strip()
        duration = float(seg.get("end", 0)) - float(seg.get("start", 0))
        
        if duration < 0.8 and filler_patterns.match(text):
            print(f"Filter Out Filler Sound: '{text}' ({duration:.2f}s)")
            continue
            
        clean_segments.append(seg)
        
    return clean_segments

def get_speech_intervals(segments, total_duration, padding_start=0.05, padding_end=0.1, merge_threshold=0.3):
    """Detects and removes all silences longer than merge_threshold seconds (default 0.3s)."""
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
    """
    Extracts Thai Buddhist Year (พ.ศ. 25XX) mentioned in transcription segments.
    Returns earliest year found (e.g. 2510, 2525, 2533) or 9999 if not found.
    """
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
        earliest_year = min(found_years)
        print(f"  • Extracted Buddhist Year: พ.ศ. {earliest_year}")
        return earliest_year
    return 9999

def render_multi_video_master(video_items, output_path, zoom_perc=120):
    """
    Stitches multiple raw video clips into a SINGLE master video ('วิดีโอเดียวจบ'):
    - video_items: list of dicts [{'path': p, 'intervals': [(s,e),...], 'width': w, 'height': h}, ...]
    - Applies Dynamic Punch-in Zoom (100% -> 120%) across segments.
    - Outputs 9:16 vertical 60fps video.
    """
    filter_complex = []
    video_maps = []
    audio_maps = []
    
    ffmpeg_inputs = []
    total_segments = 0
    
    for input_idx, item in enumerate(video_items):
        ffmpeg_inputs.extend(["-i", item["path"]])
        crop_100, crop_zoom = get_crop_filters(item["width"], item["height"], zoom_percentage=zoom_perc)
        
        for seg_idx, (start, end) in enumerate(item["intervals"]):
            v_raw_name = f"[vraw_{input_idx}_{seg_idx}]"
            v_name = f"[v_{input_idx}_{seg_idx}]"
            a_name = f"[a_{input_idx}_{seg_idx}]"
            
            filter_complex.append(f"[{input_idx}:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS{v_raw_name}")
            filter_complex.append(f"[{input_idx}:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS{a_name}")
            
            crop_fmt = crop_100 if (total_segments % 2 == 0) else crop_zoom
            filter_complex.append(f"{v_raw_name}{crop_fmt}{v_name}")
            
            video_maps.append(v_name)
            audio_maps.append(a_name)
            total_segments += 1
            
    if total_segments == 0:
        print("No valid speech segments found across video files.")
        return False
        
    concat_inputs = "".join(f"{v}{a}" for v, a in zip(video_maps, audio_maps))
    concat_filter = f"{concat_inputs}concat=n={total_segments}:v=1:a=1[vfinal][aconcat]"
    filter_complex.append(concat_filter)
    
    filter_complex_str = ";".join(filter_complex)
    
    dir_out = os.path.dirname(os.path.abspath(output_path))
    pid = os.getpid()
    temp_out = os.path.join(dir_out, f"_ffmpeg_master_out_{pid}.mp4")
    
    if os.path.exists(temp_out):
        try:
            os.remove(temp_out)
        except Exception:
            pass
            
    cmd = ["ffmpeg", "-y"] + ffmpeg_inputs + [
        "-filter_complex", filter_complex_str,
        "-map", "[vfinal]", "-map", "[aconcat]",
        "-r", "60",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        temp_out
    ]
    
    print(f"\n🎬 Rendering Master Single Output Video ({os.path.basename(output_path)}) from {len(video_items)} clips...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        print(f"FFmpeg master stitch error: {result.stderr.decode('utf-8', errors='ignore')}")
        if os.path.exists(temp_out):
            try:
                os.remove(temp_out)
            except Exception:
                pass
        return False
        
    try:
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_out, output_path)
        print(f"✅ Master Single Output Video created successfully: {output_path}")
        return True
    except Exception as e:
        print(f"Error renaming master output file: {e}")
        return False

def process_all_raw_videos_as_single_master(raw_video_paths):
    r"""
    MULTI-TAKE CLEAN & STITCH MODE:
    When multiple video files are placed in Z:\AI\EDIT AI\RW:
    1. Sorts raw video files chronologically by creation timestamp / filename.
    2. Transcribes every raw video file with Whisper STT (th).
    3. Extracts พ.ศ. (Thai Buddhist Year) if mentioned.
    4. Removes silences > 0.3s and stutters from every file.
    5. Stitches all clips into A SINGLE MASTER OUTPUT VIDEO ('RAW_VDO_COMBINED.mp4').
    6. Moves processed raw files to Z:\AI\EDIT AI\RW\processed and records SHA-256 hashes.
    """
    cleanup_old_raw_files(hours_threshold=48)
    
    print(f"\n=======================================================")
    print(f"🎬 Processing {len(raw_video_paths)} RAW Videos into RAW_VDO_COMBINED.mp4")
    print(f"=======================================================\n")
    
    # Load Whisper model
    import whisper
    print(f"Loading Whisper model '{WHISPER_MODEL_NAME}'...")
    model = whisper.load_model(WHISPER_MODEL_NAME)
    
    feedback = line_bot_manager.load_user_feedback()
    silence_thresh = float(feedback.get("silence_threshold", 0.3))
    zoom_perc = int(feedback.get("zoom_percentage", 120))
    
    processed_video_items = []
    
    for idx, vpath in enumerate(raw_video_paths):
        print(f"\n--- Processing Take {idx+1}/{len(raw_video_paths)}: {os.path.basename(vpath)} ---")
        
        # Anti-duplicate check
        is_dup, fhash = is_duplicate_file(vpath)
        if is_dup:
            continue
            
        duration, width, height = get_video_info(vpath)
        if duration <= 0:
            print("Invalid video file duration. Skipping.")
            continue
            
        segments = get_transcript_cache(vpath)
        if segments is None:
            print("Transcribing speech (language='th')...")
            res = model.transcribe(vpath, language="th")
            segments = res.get("segments", [])
            save_transcript_cache(vpath, segments)
            
        buddhist_year = extract_buddhist_year(segments)
        creation_time = os.path.getmtime(vpath)
        
        speech_intervals = get_speech_intervals(segments, duration, merge_threshold=silence_thresh)
        print(f"Extracted {len(speech_intervals)} non-silent speech blocks.")
        
        if speech_intervals:
            processed_video_items.append({
                "path": vpath,
                "buddhist_year": buddhist_year,
                "creation_time": creation_time,
                "intervals": speech_intervals,
                "width": width,
                "height": height,
                "hash": fhash
            })
            
    if not processed_video_items:
        print("No processable video files found.")
        return False
        
    # Sort files: Primary by Buddhist Year (พ.ศ. ascending), Secondary by file creation time
    processed_video_items.sort(key=lambda x: (x["buddhist_year"], x["creation_time"]))
    
    print("\n--- Final Video Stitch Sequence (Sorted by Created Date / พ.ศ.) ---")
    for i, item in enumerate(processed_video_items):
        yr_str = f"พ.ศ. {item['buddhist_year']}" if item['buddhist_year'] != 9999 else f"Created: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item['creation_time']))}"
        print(f"  Take {i+1}. {os.path.basename(item['path'])} ({yr_str})")
        
    next_num = get_next_raw_vdo_number(OUTPUT_DIR)
    master_clip_name = f"RAW VDO {next_num:03d}.mp4"
    master_output_path = os.path.join(OUTPUT_DIR, master_clip_name)
    combined_output_path = os.path.join(OUTPUT_DIR, "RAW_VDO_COMBINED.mp4")
    
    success = render_multi_video_master(processed_video_items, master_output_path, zoom_perc=zoom_perc)
    
    if success:
        # Create explicit RAW_VDO_COMBINED.mp4 file in output folder
        try:
            if os.path.exists(combined_output_path):
                os.remove(combined_output_path)
            shutil.copy2(master_output_path, combined_output_path)
            print(f"✅ Exported explicit combined master: {combined_output_path}")
        except Exception as e:
            print(f"Note creating combined copy: {e}")
            
        # Move raw files to processed directory & record hashes
        for item in processed_video_items:
            vpath = item["path"]
            fhash = item["hash"]
            if fhash:
                record_processed_file(vpath, fhash, [master_clip_name, "RAW_VDO_COMBINED.mp4"])
                
            if os.path.exists(vpath) and os.path.dirname(os.path.abspath(vpath)) == os.path.abspath(INPUT_DIR):
                dest_path = os.path.join(PROCESSED_DIR, os.path.basename(vpath))
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    os.rename(vpath, dest_path)
                    print(f"📁 Moved raw take file to: {dest_path}")
                except Exception as e:
                    print(f"Error moving file to processed dir: {e}")
                    
        line_bot_manager.send_completion_report(next_num, next_num, 1)
        return True
    else:
        print("Failed to render master single output video.")
        return False

def check_file_stability(file_path):
    """Waits for file size to stabilize to ensure copy operation is complete."""
    try:
        last_size = os.path.getsize(file_path)
    except OSError:
        return False
        
    time.sleep(5)
    
    while True:
        try:
            curr_size = os.path.getsize(file_path)
        except OSError:
            return False
            
        if curr_size == last_size:
            try:
                with open(file_path, 'rb') as f:
                    pass
                break
            except IOError:
                pass
        else:
            last_size = curr_size
            
        time.sleep(5)
        
    return True

def get_target_raw_video_files():
    """Checks INPUT_DIR (RW) for video files."""
    supported_extensions = ("*.mp4", "*.mov", "*.mkv", "*.avi", "*.flv", "*.ts", "*.webm")
    raw_files = []
    for ext in supported_extensions:
        raw_files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
    raw_files = [f for f in raw_files if os.path.isfile(f) and not os.path.basename(f).startswith("_")]
    return raw_files

def watch_folder():
    """Watches the input directory for video files and processes them as a Single Master Video."""
    print(f"Starting Video-AutoCutter-Agent v5.0 (Multi-Take Clean & Stitch Mode)...")
    print(f"Input Watch Folder: {INPUT_DIR}")
    print(f"Output Master Target: {os.path.join(OUTPUT_DIR, 'RAW_VDO_COMBINED.mp4')}")
    print(f"Processed Cleanup Folder: {PROCESSED_DIR}")
    print(f"Smart Anti-Duplicate Check: Active (SHA-256)")
    print(f"Silence Cut Threshold: > 0.3s")
    print(f"Storage Maintenance: Auto-delete raw files > 48 hours")
    
    while True:
        raw_videos = get_target_raw_video_files()
        if raw_videos:
            print(f"\n[Watch Folder] Detected {len(raw_videos)} raw video file(s) in {INPUT_DIR}...")
            stable_videos = [v for v in raw_videos if check_file_stability(v)]
            if stable_videos:
                try:
                    process_all_raw_videos_as_single_master(stable_videos)
                except Exception as e:
                    print(f"Fatal error processing videos: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            time.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        watch_folder()
    else:
        raw_videos = get_target_raw_video_files()
        if raw_videos:
            process_all_raw_videos_as_single_master(raw_videos)
        else:
            print(f"No raw video files currently found in {INPUT_DIR}.")
            print("Entering folder watcher mode (waiting for incoming files in RW)...")
            watch_folder()
