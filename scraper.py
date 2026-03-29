import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    log(f"--- 3/30 最終検証スキャン: {now.strftime('%H:%M:%S')} ---")
    
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            log("【競輪】Kドリームスへ接続中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)
            
            # デバッグ写真は継続
            await page.screenshot(path="debug_kdreams.png", full_page=True)

            soup = BeautifulSoup(await page.content(), "html.parser")
            blocks = soup.select(".kaisai-list")
            log(f"  -> 開催場を {len(blocks)} 件検出")

            for block in blocks:
                track_tag = block.select_one(".velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # ブロック内の全テキストを取得（改行や空白を正規化）
                text = block.get_text(separator=' ', strip=True)
                
                # 【超強力検索】
                # 番号: 数字の後に「R」があるもの（間に空白・改行があってもOK）
                # 時刻: 数字 : 数字 の形式（全角・半角・空白に対応）
                found_races = re.findall(r'(\d+)\s*R', text)
                found_times = re.findall(r'(\d{1,2}\s*[:：]\s*\d{2})', text)
                
                log(f"    - {track_name}: 番号{len(found_races)}件 / 時刻{len(found_times)}件")

                # 見つかった順番通りにペアにする
                if len(found_races) > 0 and len(found_races) <= len(found_times):
                    for i in range(len(found_races)):
                        r_num = found_races[i] + "R"
                        t_str = found_times[i].replace(" ", "").replace("：", ":") # 形式を整える
                        
                        races_data.append({
                            "track": track_name, 
                            "race_num": r_num, 
                            "time_str": t_str
                        })
            
            log(f"  -> 合計 {len(races
