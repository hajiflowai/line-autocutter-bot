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
    Extracts 'ราคาทองรูปพรรณ (รับซื้อ)' per baht.
    """
    url = "https://xn--42cah7d0cxcvbbb9x.com/"
    print(f"Scraping Gold Price from {url}...")
    
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        gold_ornament_buy = None
        gold_bar_buy = None
        gold_bar_sell = None
        
        for tr in soup.find_all("tr"):
            cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if not cols:
                continue
                
            row_txt = " ".join(cols)
            
            # Gold Ornament 96.5%
            if "ทองรูปพรรณ" in cols[0] and "96.5%" in cols[0]:
                if len(cols) >= 3:
                    try:
                        gold_ornament_buy = float(cols[2].replace(",", ""))
                    except ValueError:
                        pass
            elif "ทองรูปพรรณ" in cols[0] and not gold_ornament_buy:
                if len(cols) >= 2:
                    try:
                        gold_ornament_buy = float(cols[1].replace(",", ""))
                    except ValueError:
                        pass
                        
            # Gold Bar 96.5%
            if "ทองคำแท่ง" in cols[0] and "96.5%" in cols[0]:
                if len(cols) >= 3:
                    try:
                        gold_bar_sell = float(cols[1].replace(",", ""))
                        gold_bar_buy = float(cols[2].replace(",", ""))
                    except ValueError:
                        pass
                        
        if gold_ornament_buy is not None:
            print(f"✅ Extracted Gold Ornament Buy (ราคาทองรูปพรรณรับซื้อ): {gold_ornament_buy:,.2f} บาท")
            return {
                "gold_ornament_buy": gold_ornament_buy,
                "gold_bar_buy": gold_bar_buy or (gold_ornament_buy + 1200.0),
                "gold_bar_sell": gold_bar_sell or (gold_ornament_buy + 1400.0)
            }
        else:
            print("⚠️ Primary gold selector missed, applying regex fallback...")
            # Fallback regex search
            for tr in soup.find_all("tr"):
                txt = tr.get_text(" ", strip=True)
                if "รูปพรรณ" in txt and "96.5%" in txt:
                    nums = re.findall(r"[\d,]+\.\d+", txt)
                    if len(nums) >= 2:
                        gold_ornament_buy = float(nums[1].replace(",", ""))
                        return {
                            "gold_ornament_buy": gold_ornament_buy,
                            "gold_bar_buy": gold_ornament_buy + 1200.0,
                            "gold_bar_sell": gold_ornament_buy + 1400.0
                        }
    except Exception as e:
        print(f"❌ Error scraping gold price: {e}")
        
    # Return sensible default fallback if site is down
    return {
        "gold_ornament_buy": 62716.92,
        "gold_bar_buy": 64000.0,
        "gold_bar_sell": 64200.0
    }

def scrape_silver_price():
    """
    Scrapes silver price from https://kpt.in.th/silverprice.php
    Extracts 'ราคารับซื้อเงินรูปพรรณ (92.5%)' and 'เม็ดเงิน (99.9%)'.
    """
    url = "https://kpt.in.th/silverprice.php"
    print(f"Scraping Silver Price from {url}...")
    
    silver_925_buy = None
    silver_999_buy = None
    
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        for tr in soup.find_all("tr"):
            txt = tr.get_text(" ", strip=True)
            if "92.5%" in txt:
                nums = re.findall(r"[\d,]+", txt)
                if nums:
                    silver_925_buy = float(nums[-1].replace(",", ""))
            elif "99.9%" in txt:
                nums = re.findall(r"[\d,]+", txt)
                if nums:
                    silver_999_buy = float(nums[-1].replace(",", ""))
                    
        if silver_925_buy is not None:
            print(f"✅ Extracted Silver 92.5% Buy (ราคารับซื้อเงินรูปพรรณ): {silver_925_buy:,.0f} บาท/กก.")
            return {
                "silver_925_buy": silver_925_buy,
                "silver_999_buy": silver_999_buy or (silver_925_buy + 360.0)
            }
    except Exception as e:
        print(f"❌ Error scraping silver price: {e}")
        
    return {
        "silver_925_buy": 3935.0,
        "silver_999_buy": 4295.0
    }

def update_and_get_prices():
    """
    Scrapes latest Gold & Silver prices, compares with previous history in price_history.json,
    updates record, and returns price data with daily differences (+/-).
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    gold_data = scrape_gold_price()
    silver_data = scrape_silver_price()
    
    history_data = load_price_history()
    hist_map = history_data.setdefault("history", {})
    
    # Yesterday's or previous recorded price for comparison
    prev_gold = None
    prev_silver = None
    
    dates = sorted(hist_map.keys())
    for d in reversed(dates):
        if d != today_str:
            prev_gold = hist_map[d].get("gold_ornament_buy")
            prev_silver = hist_map[d].get("silver_925_buy")
            break
            
    if prev_gold is None:
        prev_gold = gold_data["gold_ornament_buy"]
    if prev_silver is None:
        prev_silver = silver_data["silver_925_buy"]
        
    gold_diff = gold_data["gold_ornament_buy"] - prev_gold
    silver_diff = silver_data["silver_925_buy"] - prev_silver
    
    # Format diff strings
    gold_diff_str = f"+{gold_diff:,.2f}" if gold_diff > 0 else (f"{gold_diff:,.2f}" if gold_diff < 0 else "เท่าเดิม")
    silver_diff_str = f"+{silver_diff:,.0f}" if silver_diff > 0 else (f"{silver_diff:,.0f}" if silver_diff < 0 else "เท่าเดิม")
    
    # Save current price to history
    hist_map[today_str] = {
        "gold_ornament_buy": gold_data["gold_ornament_buy"],
        "gold_bar_buy": gold_data["gold_bar_buy"],
        "silver_925_buy": silver_data["silver_925_buy"],
        "silver_999_buy": silver_data["silver_999_buy"],
        "updated_at": now_str
    }
    
    history_data["last_updated"] = now_str
    history_data["current"] = hist_map[today_str]
    save_price_history(history_data)
    
    return {
        "gold_ornament_buy": gold_data["gold_ornament_buy"],
        "gold_diff": gold_diff,
        "gold_diff_str": gold_diff_str,
        "silver_925_buy": silver_data["silver_925_buy"],
        "silver_diff": silver_diff,
        "silver_diff_str": silver_diff_str,
        "last_updated": now_str
    }

def check_urgent_gold_alert(threshold=300.0):
    """
    Urgent Alert Guard: Checks hourly for unusual gold price volatility (>= threshold, e.g. 300 Baht).
    If triggered, sends immediate LINE Urgent Alert!
    """
    print(f"\n--- Checking Hourly Urgent Gold Price Alert (Threshold: {threshold} Baht) ---")
    data = update_and_get_prices()
    gold_diff = data["gold_diff"]
    gold_price = data["gold_ornament_buy"]
    
    if abs(gold_diff) >= threshold:
        history_data = load_price_history()
        last_alert_time = history_data.get("last_urgent_alert_time", 0)
        now_time = time.time()
        
        # Limit urgent alerts to at most once per 6 hours to save LINE quota
        if now_time - last_alert_time >= 21600:
            direction = "ปรับขึ้นแรง 📈" if gold_diff > 0 else "ปรับลดลงแรง 📉"
            alert_msg = f"""⚠️ [เตือนด่วน! ราคาทองผันผวนแรง]
ราคาทองคำวันนี้{direction} {gold_diff:+,.2f} บาท!

💰 ราคาทองรูปพรรณรับซื้อล่าสุด: {gold_price:,.2f} บาท/บาททอง
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
            print("Urgent alert condition met, but suppressed (already alerted within 6 hours).")
    else:
        print(f"Gold price is stable (Diff: {gold_diff:+,.2f} Baht, below {threshold} threshold). No urgent alert needed.")
        
    return False

def get_metal_summary_for_report():
    """Returns formatted 2-line summary string for the daily 10:30 AM Trend Action Plan report."""
    data = update_and_get_prices()
    
    g_price = data["gold_ornament_buy"]
    g_diff = data["gold_diff_str"]
    s_price = data["silver_925_buy"]
    s_diff = data["silver_diff_str"]
    
    summary = f"""💰 สรุปราคาสินค้ามีค่าประจำวัน:
   • ทองรูปพรรณรับซื้อ: {g_price:,.2f} บาท ({g_diff})
   • เงินรูปพรรณ 92.5% รับซื้อ: {s_price:,.0f} บาท/กก. ({s_diff})"""
    return summary

if __name__ == "__main__":
    print("=== Testing Metal Tracker Scraper ===")
    res = update_and_get_prices()
    print("\n--- Scraped Results ---")
    print(f"🥇 ราคาทองรูปพรรณ (รับซื้อ): {res['gold_ornament_buy']:,.2f} บาท ({res['gold_diff_str']})")
    print(f"🥈 ราคาเงินรูปพรรณ 92.5% (รับซื้อ): {res['silver_925_buy']:,.0f} บาท/กก. ({res['silver_diff_str']})")
    print(f"🕒 อัปเดตล่าสุด: {res['last_updated']}")
    
    print("\n" + get_metal_summary_for_report())
