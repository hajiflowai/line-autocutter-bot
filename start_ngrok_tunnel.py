import os
import sys
import time
from pyngrok import ngrok, conf

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def start_ngrok(port=5000):
    """Starts Ngrok tunnel on port 5000, extracts public URL, and formats LINE Webhook URL."""
    print(f"Starting Ngrok tunnel for port {port}...")
    
    try:
        # Connect to port 5000
        tunnel = ngrok.connect(port, "http")
        public_url = str(tunnel.public_url).rstrip('/')
        
        # Ensure HTTPS scheme
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://")
            
        webhook_url = f"{public_url}/webhook"
        
        print("\n=======================================================")
        print("SUCCESS! LINE Webhook Public Ngrok URL Generated:")
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
            
        return webhook_url, tunnel
    except Exception as e:
        print(f"Error starting Ngrok tunnel: {e}")
        return None, None

if __name__ == "__main__":
    url, tun = start_ngrok(5000)
    if url:
        print("Ngrok Tunnel is ACTIVE. Keep this script running while using LINE Webhook.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping Ngrok Tunnel...")
            ngrok.disconnect(tun.public_url)
