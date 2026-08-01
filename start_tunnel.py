import os
import sys
import time
import subprocess
import re

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def start_localtunnel(port=5000):
    """Starts localtunnel via cmd/npx, captures the public URL, and formats it for LINE Webhook."""
    print(f"Starting LocalTunnel for port {port}...")
    
    cmd = ["cmd.exe", "/c", "npx", "-y", "localtunnel", "--port", str(port)]
    
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
            print(f"[localtunnel] {clean_line}")
            if "your url is:" in clean_line.lower():
                match = re.search(r"https://[^\s]+", clean_line)
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
        print("SUCCESS! LINE Webhook Public URL Generated:")
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
        print("Error: Failed to retrieve localtunnel URL within timeout.")
        process.kill()
        return None, None

if __name__ == "__main__":
    url, proc = start_localtunnel(5000)
    if url:
        print("Keep this process running while using LINE Webhook.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping LocalTunnel...")
            proc.kill()
