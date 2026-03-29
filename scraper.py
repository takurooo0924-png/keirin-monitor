import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    date_hyphen = now.strftime('%Y-%m-%d')
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0")
        page = await context.new_page()

        # --- 1. 競輪 (ColabのPandasロジックを完全再現) ---
        try:
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            await page.wait_for_timeout(7000) 
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            for block in soup.find_all(class_="kaisai-list"):
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # 表として読み込み (timer.ymlに足したlxmlを使用)
                tables = block.find_all("table")
                for tbl in tables:
                    try:
                        # Colabと同じくPandasで表を解析
                        df = pd.read_html(StringIO(str(tbl)))[0]
                        for _, row in df.iterrows():
                            r_num = str(row.iloc[0])
                            if "R" in r_num:
                                # 2列目から時間を抽出
                                time_m = re.search(r'(\d{1,2}:\d{2})', str(row.iloc[1]))
                                if time_m and "結果" not in str(row.iloc[1]):
                                    races_data.append({
                                        "track": track_name, "race_num": r_num, "time_str": time_m.group(1)
                                    })
                    except: continue
        except Exception as e:
            print(f"Keirin Error: {e}")

        # --- 2. オートレース (12R狙い撃ち + 待機強化) ---
        tracks_auto = {"飯塚": "iizuka", "川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "山陽": "sanyou"}
        for name, roma in tracks_auto.items():
            try:
                url = f"https://autorace.jp/race_info/Program/{roma}/{date_hyphen}_12/program"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # ★重要：証拠写真の「グレーの棒」対策。文字が出るまで最大15秒待つ
                await page.wait_for_selector("text=投票締切", timeout=15000)
                
                content = await page.content()
                m = re.search(r'投票締切\s*(\d{1,2}:\d{2})', content)
                if m:
                    races_data.append({
                        "track": f"{name}オート", "race_num": "12R", "time_str": m.group(1)
                    })
            except: continue

        await browser.close()

    # --- 保存処理 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # ミッドナイト補正
        if now.hour >= 20 and h < 5: dt += timedelta(days=1)
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"],
                "race_num": r["race_num"],
                "time_str": r["time_str"],
                "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
