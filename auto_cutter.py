import os
import sys
import time
import glob
import json
import re
import subprocess
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

def get_crop_filters(width, height, zoom_percentage=115):
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
            
    # 100% Zoom (Normal shot)
    filter_100 = f"crop={crop_w}:{crop_h},scale=1080:1920,setsar=1"
    
    # Zoom % (Punch-in close-up shot)
    zoom_factor = float(zoom_percentage) / 100.0
    zoom_w = int(crop_w / zoom_factor) // 2 * 2
    zoom_h = int(crop_h / zoom_factor) // 2 * 2
    filter_zoom = f"crop={zoom_w}:{zoom_h},scale=1080:1920,setsar=1"
    
    return filter_100, filter_zoom

def get_speech_intervals(segments, total_duration, padding_start=0.05, padding_end=0.1, merge_threshold=0.3):
    """
    AUTO SILENCE CUT: Automatically detects and removes all silences longer than merge_threshold seconds (default 0.3s).
    Pads speech segments lightly to preserve word boundaries and groups continuous speech blocks.
    """
    raw_intervals = []
    for seg in segments:
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

def is_overlapping(s1, e1, s2, e2):
    """Returns True if interval [s1, e1] overlaps with interval [s2, e2]."""
    return max(s1, s2) < min(e1, e2)

def select_10_clips(intervals, total_duration, min_duration=30.0, max_duration=60.0, used_intervals=None):
    """
    Finds exactly 10 non-overlapping NEW clips from the speech intervals.
    Each clip represents a coherent topic/story block of duration 30s-60s with silence cut out.
    Skips any candidate clips that overlap with previously used interval ranges.
    """
    if used_intervals is None:
        used_intervals = []
        
    candidates = []
    n = len(intervals)
    
    for i in range(n):
        curr_duration = 0.0
        for j in range(i, n):
            curr_duration += (intervals[j][1] - intervals[j][0])
            if min_duration <= curr_duration <= max_duration:
                start_time = intervals[i][0]
                end_time = intervals[j][1]
                
                # Check for overlap with previously exported clips
                has_history_overlap = False
                for u_start, u_end in used_intervals:
                    if is_overlapping(start_time, end_time, u_start, u_end):
                        has_history_overlap = True
                        break
                        
                if not has_history_overlap:
                    candidates.append({
                        "start_idx": i,
                        "end_idx": j,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": curr_duration,
                        "sub_intervals": intervals[i:j+1]
                    })
            elif curr_duration > max_duration:
                break
                
    if not candidates:
        print("No NEW valid candidate topic clips of duration 30s-60s could be formed.")
        return []
        
    selected_clips = []
    last_end_block_idx = -1
    
    for m in range(10):
        target_start = m * (total_duration / 10)
        best_candidate = None
        best_diff = float('inf')
        
        for cand in candidates:
            if cand["start_idx"] > last_end_block_idx:
                diff = abs(cand["start_time"] - target_start)
                if diff < best_diff:
                    best_diff = diff
                    best_candidate = cand
                    
        if best_candidate is not None:
            selected_clips.append(best_candidate)
            last_end_block_idx = best_candidate["end_idx"]
            
    return selected_clips

def render_clip(input_path, output_path, intervals, crop_filter_100, crop_filter_zoom):
    """
    Stitches speech intervals together and applies DYNAMIC PUNCH-IN:
    Alternates scale between 100% and zoom_percentage% at every sentence boundary for a multi-camera jump cut effect.
    Outputs clean vertical 9:16 video @ 60fps (NO subtitles, NO text, NO overlays).
    """
    filter_complex = []
    video_maps = []
    audio_maps = []
    
    for idx, (start, end) in enumerate(intervals):
        v_raw_name = f"[vraw{idx}]"
        v_name = f"[v{idx}]"
        a_name = f"[a{idx}]"
        
        filter_complex.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS{v_raw_name}")
        filter_complex.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS{a_name}")
        
        crop_fmt = crop_filter_100 if (idx % 2 == 0) else crop_filter_zoom
        filter_complex.append(f"{v_raw_name}{crop_fmt}{v_name}")
        
        video_maps.append(v_name)
        audio_maps.append(a_name)
        
    concat_inputs = "".join(f"{v}{a}" for v, a in zip(video_maps, audio_maps))
    concat_filter = f"{concat_inputs}concat=n={len(intervals)}:v=1:a=1[vfinal][aconcat]"
    filter_complex.append(concat_filter)
    
    filter_complex_str = ";".join(filter_complex)
    
    dir_in = os.path.dirname(os.path.abspath(input_path))
    dir_out = os.path.dirname(os.path.abspath(output_path))
    pid = os.getpid()
    
    temp_in = os.path.join(dir_in, f"_ffmpeg_in_{pid}.mp4")
    temp_out = os.path.join(dir_out, f"_ffmpeg_out_{pid}.mp4")
    
    created_link = False
    try:
        if os.path.exists(temp_in):
            os.remove(temp_in)
        os.link(input_path, temp_in)
        created_link = True
        real_in = temp_in
    except Exception as e:
        print(f"Warning: Failed to create temp hardlink ({e}). Using direct path.")
        real_in = input_path
        
    if os.path.exists(temp_out):
        try:
            os.remove(temp_out)
        except Exception:
            pass
            
    cmd = [
        "ffmpeg", "-y", "-i", real_in,
        "-filter_complex", filter_complex_str,
        "-map", "[vfinal]", "-map", "[aconcat]",
        "-r", "60",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        temp_out
    ]
    
    print(f"Rendering {os.path.basename(output_path)} with Dynamic Punch-in...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if created_link and os.path.exists(temp_in):
        try:
            os.remove(temp_in)
        except Exception:
            pass
            
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr.decode('utf-8', errors='ignore')}")
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
    except Exception as e:
        print(f"Error renaming output file to {output_path}: {e}")
        if os.path.exists(temp_out):
            try:
                os.remove(temp_out)
            except Exception:
                pass
        return False
        
    return True

def process_video(video_path, move_to_processed=True):
    """Processes a RAW video file with Auto Silence Cut and Dynamic Punch-in based on LINE feedback parameters."""
    start_time = time.time()
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    print(f"\n--- Starting processing for: {video_path} ---")
    
    # Load dynamic user feedback parameters from LINE chat
    feedback = line_bot_manager.load_user_feedback()
    silence_thresh = float(feedback.get("silence_threshold", 0.3))
    zoom_perc = int(feedback.get("zoom_percentage", 115))
    print(f"Active Editing Config -> Silence Threshold: {silence_thresh}s, Zoom Scale: {zoom_perc}%")
    
    # 1. Gather video information
    duration, width, height = get_video_info(video_path)
    if duration <= 0:
        print("Invalid video file or failed to extract duration.")
        return False
        
    print(f"Video specs: {width}x{height}, duration: {duration:.2f}s")
    
    # 2. Get or compute Whisper transcription segments
    segments = get_transcript_cache(video_path)
    if segments is None:
        print(f"Loading Whisper model '{WHISPER_MODEL_NAME}'...")
        import whisper
        model = whisper.load_model(WHISPER_MODEL_NAME)
        
        print("Transcribing video speech (language='th')...")
        result = model.transcribe(video_path, language="th")
        segments = result.get("segments", [])
        print(f"Transcription finished. Detected {len(segments)} speech segments.")
        save_transcript_cache(video_path, segments)
    else:
        print(f"Using cached transcription with {len(segments)} speech segments.")
        
    # 3. Detect speech intervals with AUTO SILENCE CUT
    speech_intervals = get_speech_intervals(segments, duration, merge_threshold=silence_thresh)
    print(f"Formed {len(speech_intervals)} non-silent topic blocks (Auto Silence Cut <{silence_thresh}s).")
    
    # 4. Load history of previously exported clip intervals
    history = load_history()
    video_history = history.get(base_name, {"used_intervals": []})
    used_intervals = video_history.get("used_intervals", [])
    
    print(f"Previously used intervals count for this video: {len(used_intervals)}")
    
    # 5. Select 10 NEW non-overlapping clips (skipping used intervals)
    selected_clips = select_10_clips(speech_intervals, duration, used_intervals=used_intervals)
    print(f"Selected {len(selected_clips)} NEW unique topic clips for export.")
    
    if not selected_clips:
        print("Error: No new unique topic clips could be sliced.")
        return False
        
    crop_100, crop_zoom = get_crop_filters(width, height, zoom_percentage=zoom_perc)
    
    # 6. Render selected clips with DYNAMIC PUNCH-IN and sequential RAW VDO XXX.mp4 naming
    success_count = 0
    new_used_intervals = list(used_intervals)
    start_vdo_num = get_next_raw_vdo_number(OUTPUT_DIR)
    
    for idx, clip in enumerate(selected_clips):
        next_vdo_num = start_vdo_num + idx
        clip_name = f"RAW VDO {next_vdo_num:03d}.mp4"
        output_path = os.path.join(OUTPUT_DIR, clip_name)
        
        print(f"Processing Clip {idx+1}/{len(selected_clips)} ({clip_name}): duration = {clip['duration']:.2f}s")
        
        success = render_clip(video_path, output_path, clip["sub_intervals"], crop_100, crop_zoom)
        if success:
            success_count += 1
            new_used_intervals.append([clip["start_time"], clip["end_time"]])
            print(f"Successfully exported: {clip_name}")
        else:
            print(f"Failed to export clip {idx+1}")
            
    # Save updated history
    history[base_name] = {
        "used_intervals": new_used_intervals
    }
    save_history(history)
    
    # 7. Post-processing and LINE Bi-Directional Report
    elapsed = time.time() - start_time
    print(f"\nProcessing finished in {elapsed:.2f} seconds. Success count: {success_count}/{len(selected_clips)}")
    
    if success_count > 0:
        end_vdo_num = start_vdo_num + success_count - 1
        
        if move_to_processed and os.path.exists(video_path) and os.path.dirname(os.path.abspath(video_path)) == os.path.abspath(INPUT_DIR):
            dest_path = os.path.join(PROCESSED_DIR, os.path.basename(video_path))
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(video_path, dest_path)
                print(f"Moved raw video to {dest_path}")
            except Exception as e:
                print(f"Error moving raw file to processed dir: {e}")
                
        # Send Bi-Directional LINE Report with AI Self-Analysis & Suggestions
        line_bot_manager.send_completion_report(start_vdo_num, end_vdo_num, success_count)
        return True
    else:
        print("No clips were successfully rendered.")
        return False

def check_file_stability(file_path):
    """Waits for file size to stabilize to ensure copy operation is complete."""
    print(f"Checking file stability for {file_path}...")
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
                print("File is locked. Waiting...")
        else:
            last_size = curr_size
            print(f"File is still copying. Size: {curr_size} bytes...")
            
        time.sleep(5)
        
    print("File is stable and ready to process.")
    return True

def get_target_video_file():
    """Checks INPUT_DIR (RW) for video files. If empty, checks PROCESSED_DIR for available videos."""
    supported_extensions = ("*.mp4", "*.mov", "*.mkv", "*.avi", "*.flv", "*.ts", "*.webm")
    
    raw_files = []
    for ext in supported_extensions:
        raw_files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
    raw_files = [f for f in raw_files if os.path.isfile(f)]
    if raw_files:
        return raw_files[0], True
        
    proc_files = []
    for ext in supported_extensions:
        proc_files.extend(glob.glob(os.path.join(PROCESSED_DIR, ext)))
    proc_files = [f for f in proc_files if os.path.isfile(f)]
    if proc_files:
        return proc_files[0], False
        
    return None, False

def watch_folder():
    """Watches the input directory for video files and processes them."""
    print(f"Starting Video-AutoCutter-Agent...")
    print(f"Input Watch Folder: {INPUT_DIR}")
    print(f"Output Folder: {OUTPUT_DIR}")
    print(f"Processed Folder: {PROCESSED_DIR}")
    print(f"LINE Bi-Directional Integration: Active")
    
    while True:
        target_video, should_move = get_target_video_file()
        if target_video:
            if check_file_stability(target_video):
                try:
                    process_video(target_video, move_to_processed=should_move)
                except Exception as e:
                    print(f"Fatal error processing {target_video}: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            time.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
        if os.path.exists(target_file) and os.path.isfile(target_file):
            process_video(target_file, move_to_processed=False)
        else:
            print(f"Specified file does not exist: {target_file}")
    else:
        try:
            target_video, should_move = get_target_video_file()
            if target_video:
                process_video(target_video, move_to_processed=should_move)
            else:
                print("No video file found in RW or processed directory.")
        except KeyboardInterrupt:
            print("\nAgent stopped by user.")
