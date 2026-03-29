import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

async def fetch_keirin(page):
    races = []
    try:
        log("【競輪】Kドリームス取得中...")
        await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        blocks = await page.query_selector_all(".kaisai-list")
        for block in blocks:
            track_tag = await block.query_selector(".velodrome")
            if not track_tag: continue
            track = (await track_tag.inner_text()).replace("競輪", "").strip()
            text = await block.inner_text()
            nums = re.findall(r'(\d+)\s*R', text)
            times = re.findall(r'(\d{1,2})\s*[:：]\s*(\d{2})', text)
            if len(nums) > 0 and len(nums) <= len(times):
                for i in range(len(nums)):
                    races.append({"track": track, "race_num": nums[i]+"R", "time": f"{times[i][0]}:{times[i][1]}"})
    except Exception as e: log(f"競輪エラー: {e}")
    return races

async def fetch_auto(page):
    races = []
    try:
        log("【オート】オッズパーク取得中...")
        today_str = datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y%m%d')
        # 開催予定ページから現在の開催場を取得
        await page.goto("https://www.oddspark.com/autorace/KaisaiYotei.do", wait_until="networkidle")
        links = await page.query_selector_all("a[href*='OneDayRaceList.do']")
        urls = list(set([await l.get_attribute("href") for l in links]))
        
        for url in urls:
            full_url = "https://www.oddspark.com" + url if url.startswith("/") else url
            await page.goto(full_url, wait_until="networkidle")
            track_tag = await page.query_selector(".view_data_01") # 場名
            track = (await track_tag.inner_text()).split()[0] if track_tag else "不明"
            
            # 「16:33 締切」という文字をそのまま探すロジック（計算なし）
            content = await page.content()
            # 正規表現で「レース番号」と「締切」をセットで抜く
            items = re.findall(r'(\d+)R.*?(\d{1,2}:\d{2})\s*締切', content, re.DOTALL)
            for item in items:
                races.append({"track": track, "race_num": item[0]+"R", "time": item[1]})
    except Exception as e: log(f"オートエラー: {e}")
    return races

async def main():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    all_races = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 競輪とオートを両方取得
        all_races.extend(await fetch_keirin(page))
        all_races.extend(await fetch_auto(page))
        
        await browser.close()

    # 重複削除と未来のレースのみ抽出
    parsed = []
    seen = set()
    for r in all_races:
        key = f"{r['track']}_{r['race_num']}"
        if key in seen: continue
        try:
            h, m = map(int, r["time"].split(':'))
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt < now - timedelta(hours=6): dt += timedelta(days=1)
            if dt > now:
                parsed.append({"id": key, "track": r["track"], "race_num": r["race_num"], "time_str": r["time"], "deadline": dt.isoformat()})
                seen.add(key)
        except: continue

    parsed.sort(key=lambda x: x["deadline"])
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    log(f"--- 最終集計: {len(parsed)} 件を保存 ---")

if __name__ == "__main__":
    asyncio.run(main())
