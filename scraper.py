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
    # オートレース用 (YYYY-MM-DD) - Colabと同じ形式
    date_hyphen = now.strftime('%Y-%m-%d')
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0")
        page = await context.new_page()

        # --- 1. 競輪 (Colabの力技抽出を再現) ---
        try:
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=30000)
            await page.wait_for_timeout(5000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            for block in soup.find_all(class_="kaisai-list"):
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.text.replace("競輪", "").strip()
                
                # ブロック内の全テキストから時刻(00:00)を抽出
                block_text = block.get_text()
                times = re.findall(r'(\d{1,2}:\d{2})', block_text)
                
                # 「結果」が含まれるレースは終了とみなす
                for i, t_str in enumerate(times):
                    r_num = f"{i+1}R"
                    # Colabと同様、そのレース番号付近に「結果」の文字がなければ採用
                    if f"{r_num} 結果" not in block_text:
                        races_data.append({
                            "track": track_name,
                            "race_num": r_num,
                            "time_str": t_str
                        })
        except Exception as e:
            print(f"Keirin Error: {e}")

        # --- 2. オートレース (12R狙い撃ち) ---
        tracks_auto = {"川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "飯塚": "iizuka", "山陽": "sanyou"}
        for name, roma in tracks_auto.items():
            try:
                url = f"https://autorace.jp/race_info/Program/{roma}/{date_hyphen}_12/program"
                await page.goto(url, wait_until="networkidle", timeout=20000)
                content = await page.content()
                # Colabの「投票締切 XX:XX」を抽出する正規表現
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

    # --- 共通の保存処理 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # 日またぎ(ミッドナイト)補正
        if now.hour >= 20 and h < 5: dt += timedelta(days=1)
        
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"],
                "race_num": r["race_num"],
                "time_str": r["time_str"],
                "deadline": dt.isoformat()
            })

    # 時間順にソート
    parsed_results.sort(key=lambda x: x["deadline"])
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
