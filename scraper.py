import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
import pandas as pd
from bs4 import BeautifulSoup
from io import StringIO
from playwright.async_api import async_playwright

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    today_date = now.strftime('%Y%m%d') # オートレース用 (YYYYMMDD)
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0")
        page = await context.new_page()

        # --- 1. 競輪 (Colabの判定ロジックを優先) ---
        try:
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=30000)
            await page.wait_for_timeout(3000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            for block in soup.find_all(class_="kaisai-list"):
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.text.replace("競輪", "").strip()
                
                # 全レース(1R-12R)をチェック
                tables = block.find_all("table")
                for tbl in tables:
                    df_list = pd.read_html(StringIO(str(tbl)))
                    for df in df_list:
                        for col in df.columns:
                            if isinstance(col, str) and re.match(r'^\d+R$', col):
                                val = str(df[col].iloc[0])
                                m = re.search(r'(\d{1,2}:\d{2})', val)
                                if m and "結果" not in val and "中止" not in val:
                                    races_data.append({
                                        "track": track_name,
                                        "race_num": col,
                                        "time_str": m.group(1)
                                    })
        except Exception as e:
            print(f"競輪エラー: {e}")

        # --- 2. オートレース (12R狙い撃ちロジック) ---
        tracks_auto = {"川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "飯塚": "iizuka", "山陽": "sanyou"}
        for name, roma in tracks_auto.items():
            try:
                # Colabと同じく「最終12R」のページを直接見に行く
                url = f"https://autorace.jp/race_info/Program/{roma}/{today_date}_12/program"
                await page.goto(url, wait_until="networkidle", timeout=20000)
                content = await page.content()
                
                # 「投票締切 XX:XX」を抽出
                m = re.search(r'投票締切\s*(\d{1,2}:\d{2})', content)
                if m:
                    races_data.append({
                        "track": f"{name}オート",
                        "race_num": "12R",
                        "time_str": m.group(1)
                    })
            except:
                continue # 開催がない場はスルー

        await browser.close()

    # --- データの整理と保存 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        # 日またぎ補正 (Colab基準)
        if now.hour >= 20 and h < 5: dt += timedelta(days=1)
        
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"],
                "race_num": r["race_num"],
                "time_str": r["time_str"],
                "deadline": dt.isoformat()
            })

    # 近い順に並び替え
    parsed_results.sort(key=lambda x: x["deadline"])

    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
