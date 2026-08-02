import os
import sys
import time
import datetime
import json
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Force UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project dir is in sys.path
sys.path.append(r"Z:\AI\EDIT AI")
import line_bot_manager

load_dotenv()

PRICE_HISTORY_FILE = r"Z:\AI\EDIT AI\price_history.json"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Conversion constants
GRAMS_PER_BAHT_GOLD = 15.16  # 1 บาททอง = 15.16 กรัม

def load_price_history():
    """Loads price history data from JSON file."""
    if os.path.exists(PRICE_HISTORY_FILE):
        try:
            with open(PRICE_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading price history: {e}")
    return {
        "last_updated": "",
        "current": {},
        "history": {},
        "last_urgent_alert_time": 0
    }

def save_price_history(data):
    """Saves price history data to JSON file."""
    try:
        with open(PRICE_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving price history: {e}")

def scrape_gold_price():
    """
    Scrapes gold price from https://ราคาทองวันนี้.com/ (https://xn--42cah7d0cxcvbbb9x.com/)
    Extracts 'ราคาทองรูปพรรณ (รับซื้อ)' per baht and calculates THB/Gram (1 บาททอง = 15.16g).
    """
    url = "https://xn--42cah7d0cxcvbbb9x.com/"
    print(f"Scraping Gold Price from {url}...")
    
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        gold_ornament_buy_baht = None
        
        for tr in soup.find_all("tr"):
            cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if not cols:
                continue
                
            # Gold Ornament 96.5%
            if "ทองรูปพรรณ" in cols[0] and "96.5%" in cols[0]:
                if len(cols) >= 3:
                    try:
                        gold_ornament_buy_baht = float(cols[2].replace(",", ""))
                    except ValueError:
                        pass
            elif "ทองรูปพรรณ" in cols[0] and not gold_ornament_buy_baht:
                if len(cols) >= 2:
                    try:
                        gold_ornament_buy_baht = float(cols[1].replace(",", ""))
                    except ValueError:
                        pass
                        
        if gold_ornament_buy_baht is not None:
            gold_per_gram = gold_ornament_buy_baht / GRAMS_PER_BAHT_GOLD
            print(f"✅ Extracted Gold Buy: {gold_ornament_buy_baht:,.2f} THB/Baht -> {gold_per_gram:,.2f} THB/Gram")
            return {
                "gold_ornament_buy_baht": gold_ornament_buy_baht,
                "gold_per_gram": gold_per_gram
            }
        else:
            print("⚠️ Primary gold selector missed, applying regex fallback...")
            for tr in soup.find_all("tr"):
                txt = tr.get_text(" ", strip=True)
                if "รูปพรรณ" in txt and "96.5%" in txt:
                    nums = re.findall(r"[\d,]+\.\d+", txt)
                    if len(nums) >= 2:
                        gold_ornament_buy_baht = float(nums[1].replace(",", ""))
                        gold_per_gram = gold_ornament_buy_baht / GRAMS_PER_BAHT_GOLD
                        return {
                            "gold_ornament_buy_baht": gold_ornament_buy_baht,
                            "gold_per_gram": gold_per_gram
                        }
    except Exception as e:
        print(f"❌ Error scraping gold price: {e}")
        
    default_baht = 62716.92
    return {
        "gold_ornament_buy_baht": default_baht,
        "gold_per_gram": default_baht / GRAMS_PER_BAHT_GOLD
    }

def scrape_silver_price():
    """
    Scrapes silver price from https://kpt.in.th/silverprice.php
    Extracts 'ราคารับซื้อเงินรูปพรรณ (92.5%)' per kg and calculates THB/Gram (divide by 1,000g).
    """
    url = "https://kpt.in.th/silverprice.php"
    print(f"Scraping Silver Price from {url}...")
    
    silver_925_buy_kg = None
    
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        for tr in soup.find_all("tr"):
            txt = tr.get_text(" ", strip=True)
            if "92.5%" in txt:
                nums = re.findall(r"[\d,]+", txt)
                if nums:
                    silver_925_buy_kg = float(nums[-1].replace(",", ""))
                    
        if silver_925_buy_kg is not None:
            silver_per_gram = silver_925_buy_kg / 1000.0
            print(f"✅ Extracted Silver Buy: {silver_925_buy_kg:,.0f} THB/Kg -> {silver_per_gram:,.2f} THB/Gram")
            return {
                "silver_925_buy_kg": silver_925_buy_kg,
                "silver_per_gram": silver_per_gram
            }
    except Exception as e:
        print(f"❌ Error scraping silver price: {e}")
        
    default_kg = 3935.0
    return {
        "silver_925_buy_kg": default_kg,
        "silver_per_gram": default_kg / 1000.0
    }

def update_and_get_prices():
    """
    Scrapes latest Gold & Silver prices in THB/Gram, compares with previous history in price_history.json,
    updates record, and returns price data with daily differences (+/- บาท/กรัม).
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    gold_data = scrape_gold_price()
    silver_data = scrape_silver_price()
    
    history_data = load_price_history()
    hist_map = history_data.setdefault("history", {})
    
    prev_gold_gram = None
    prev_silver_gram = None
    
    dates = sorted(hist_map.keys())
    for d in reversed(dates):
        if d != today_str:
            prev_gold_gram = hist_map[d].get("gold_per_gram")
            prev_silver_gram = hist_map[d].get("silver_per_gram")
            break
            
    if prev_gold_gram is None:
        prev_gold_gram = gold_data["gold_per_gram"]
    if prev_silver_gram is None:
        prev_silver_gram = silver_data["silver_per_gram"]
        
    gold_diff_gram = gold_data["gold_per_gram"] - prev_gold_gram
    silver_diff_gram = silver_data["silver_per_gram"] - prev_silver_gram
    
    # Format THB/Gram diff strings
    gold_diff_str = f"+{gold_diff_gram:,.2f}" if gold_diff_gram > 0 else (f"{gold_diff_gram:,.2f}" if gold_diff_gram < 0 else "เท่าเดิม")
    silver_diff_str = f"+{silver_diff_gram:,.2f}" if silver_diff_gram > 0 else (f"{silver_diff_gram:,.2f}" if silver_diff_gram < 0 else "เท่าเดิม")
    
    # Save current price to history
    hist_map[today_str] = {
        "gold_ornament_buy_baht": gold_data["gold_ornament_buy_baht"],
        "gold_per_gram": gold_data["gold_per_gram"],
        "silver_925_buy_kg": silver_data["silver_925_buy_kg"],
        "silver_per_gram": silver_data["silver_per_gram"],
        "updated_at": now_str
    }
    
    history_data["last_updated"] = now_str
    history_data["current"] = hist_map[today_str]
    save_price_history(history_data)
    
    return {
        "gold_per_gram": gold_data["gold_per_gram"],
        "gold_diff_gram": gold_diff_gram,
        "gold_diff_str": gold_diff_str,
        "silver_per_gram": silver_data["silver_per_gram"],
        "silver_diff_gram": silver_diff_gram,
        "silver_diff_str": silver_diff_str,
        "gold_baht_diff": gold_diff_gram * GRAMS_PER_BAHT_GOLD,
        "last_updated": now_str
    }

def check_urgent_gold_alert(threshold_baht=300.0):
    """
    Urgent Alert Guard: Checks hourly for unusual gold price volatility (>= threshold in baht, e.g. 300 Baht = ~19.78 THB/g).
    If triggered, sends immediate LINE Urgent Alert!
    """
    print(f"\n--- Checking Hourly Urgent Gold Price Alert (Threshold: {threshold_baht} Baht / ~{threshold_baht/15.16:.2f} THB/g) ---")
    data = update_and_get_prices()
    gold_baht_diff = data["gold_baht_diff"]
    gold_gram_price = data["gold_per_gram"]
    
    if abs(gold_baht_diff) >= threshold_baht:
        history_data = load_price_history()
        last_alert_time = history_data.get("last_urgent_alert_time", 0)
        now_time = time.time()
        
        if now_time - last_alert_time >= 21600:
            direction = "ปรับขึ้นแรง 📈" if gold_baht_diff > 0 else "ปรับลดลงแรง 📉"
            alert_msg = f"""⚠️ [เตือนด่วน! ราคาทองผันผวนแรง]
ราคาทองคำวันนี้{direction} {gold_baht_diff:+,.2f} บาท! ({data['gold_diff_gram']:+,.2f} บาท/กรัม)

💰 ราคาทองรูปพรรณรับซื้อล่าสุด: {gold_gram_price:,.2f} บาท/กรัม
📅 ณ เวลา: {data['last_updated']}

👉 แนะนำวางแผนการรับซื้อเหรียญทอง/ทองโบราณให้สอดคล้องกับตลาดด่วนครับ!"""
            print(alert_msg)
            success = line_bot_manager.push_line_message(alert_msg)
            if success:
                history_data["last_urgent_alert_time"] = now_time
                save_price_history(history_data)
                print("🚨 Urgent Gold Alert delivered to LINE successfully!")
            return True
    else:
        print(f"Gold price is stable (Diff: {gold_baht_diff:+,.2f} Baht / {data['gold_diff_gram']:+,.2f} THB/g). No urgent alert needed.")
        
    return False

def get_metal_summary_for_report():
    """
    Returns formatted 2-line summary string in THB/Gram for the daily 10:30 AM Trend Action Plan report.
    Format: '• ทองรูปพรรณรับซื้อ: XXX.XX บาท/กรัม' and '• เงินรูปพรรณรับซื้อ: XX.XX บาท/กรัม'
    """
    data = update_and_get_prices()
    
    g_gram = data["gold_per_gram"]
    g_diff = data["gold_diff_str"]
    s_gram = data["silver_per_gram"]
    s_diff = data["silver_diff_str"]
    
    summary = f"""💰 สรุปราคาสินค้ามีค่าประจำวัน:
   • ทองรูปพรรณรับซื้อ: {g_gram:,.2f} บาท/กรัม ({g_diff} บาท/กรัม)
   • เงินรูปพรรณรับซื้อ: {s_gram:,.2f} บาท/กรัม ({s_diff} บาท/กรัม)"""
    return summary

if __name__ == "__main__":
    print("=== Testing Metal Tracker Scraper (THB/Gram Mode) ===")
    res = update_and_get_prices()
    print("\n--- Scraped Results ---")
    print(f"🥇 ราคาทองรูปพรรณ (รับซื้อ): {res['gold_per_gram']:,.2f} บาท/กรัม ({res['gold_diff_str']} บาท/กรัม)")
    print(f"🥈 ราคาเงินรูปพรรณ (รับซื้อ): {res['silver_per_gram']:,.2f} บาท/กรัม ({res['silver_diff_str']} บาท/กรัม)")
    print(f"🕒 อัปเดตล่าสุด: {res['last_updated']}")
    
    print("\n" + get_metal_summary_for_report())
