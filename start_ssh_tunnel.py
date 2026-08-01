import os
import sys
import time
import subprocess
import re

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def start_ssh_tunnel(port=5000):
    """Starts SSH reverse tunnel via localhost.run on 127.0.0.1:5000, captures public URL, and formats Webhook URL."""
    print(f"Starting SSH tunnel via localhost.run for 127.0.0.1:{port}...")
    
    # Explicitly use 127.0.0.1 instead of localhost to prevent Windows IPv6 ::1 binding mismatch
    cmd = ["cmd.exe", "/c", "ssh", "-o", "StrictHostKeyChecking=no", "-R", f"80:127.0.0.1:{port}", "nokey@localhost.run"]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1
    )
    
    public_url = None
    start_time = time.time()
    
    while time.time() - start_time < 30:
        line = process.stdout.readline()
        if line:
            clean_line = line.strip()
            print(f"[localhost.run] {clean_line}")
            if "tunneled with tls termination" in clean_line.lower():
                match = re.search(r"https://[a-zA-Z0-9\.\-]+\.(?:lhr\.life|localhost\.run)", clean_line)
                if match:
                    public_url = match.group(0).rstrip('/')
                    break
        else:
            if process.poll() is not None:
                break
            time.sleep(0.5)
            
    if public_url:
        webhook_url = f"{public_url}/webhook"
        print("\n=======================================================")
        print("SUCCESS! LINE Webhook Public Direct URL Generated:")
        print(f"Base URL: {public_url}")
        print(f"LINE Webhook URL: {webhook_url}")
        print("=======================================================\n")
        
        url_file = r"Z:\AI\EDIT AI\LINE_WEBHOOK_URL.txt"
        try:
            with open(url_file, "w", encoding="utf-8") as f:
                f.write(f"Public Base URL: {public_url}\n")
                f.write(f"LINE Webhook URL: {webhook_url}\n")
            print(f"Saved Webhook URL to {url_file}")
        except Exception as e:
            print(f"Error saving URL file: {e}")
            
        return webhook_url, process
    else:
        print("Error: Failed to retrieve SSH tunnel URL within timeout.")
        process.kill()
        return None, None

if __name__ == "__main__":
    url, proc = start_ssh_tunnel(5000)
    if url:
        print("SSH Tunnel is ACTIVE. Keep this script running while using LINE Webhook.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping SSH Tunnel...")
            proc.kill()
