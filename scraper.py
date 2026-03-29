import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    date_hyphen = now.strftime('%Y-%m-%d') # オート用: 2026-03-29
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0")
        page = await context.new_page()

        # --- 1. 競輪 (Kドリームス) ---
        try:
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=30000)
            await page.wait_for_timeout(5000) # 読み込み待ち
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            for block in soup.find_all(class_="kaisai-list"):
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.text.replace("競輪", "").strip()
                
                # ページ全体のテキストから "00:00" 形式をすべて探す
                text = block.get_text()
                times = re.findall(r'(\d{1,2}:\d{2})', text)
                
                for i, t_str in enumerate(times):
                    # レース番号を推測(見つかった順に1R, 2R...)
                    races_data.append({
                        "track": track_name,
                        "race_num": f"{i+1}R",
                        "time_str": t_str
                    })
        except Exception as e:
            print(f"競輪エラー: {e}")

        # --- 2. オートレース (12R狙い撃ち) ---
        tracks_auto = {"川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "飯塚": "iizuka", "山陽": "sanyou"}
        for name, roma in tracks_auto.items():
            try:
                url = f"https://autorace.jp/race_info/Program/{roma}/{date_hyphen}_12/program"
                await page.goto(url, wait_until="networkidle", timeout=20000)
                content = await page.content()
                m = re.search(r'投票締切\s*(\d{1,2}:\d{2})', content)
                if m:
                    races_data.append({
                        "track": f"{name}オート",
                        "race_num": "12R",
                        "time_str": m.group(1)
                    })
            except:
                continue

        await browser.close()

    # --- 保存処理 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # 日またぎ補正
        if now.hour >=
