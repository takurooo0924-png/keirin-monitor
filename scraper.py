import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

# 以前成功した「競輪」のロジックは一切変更していません
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

# オートレース：公式サイトから「投票締切」の数字をそのまま抽出（計算なし）
async def fetch_auto(page):
    races = []
    try:
        log("【オート】公式サイト取得中...")
        today_str = datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d')
        await page.goto("https://autorace.jp/", wait_until="networkidle")
        
        # 本日の開催場（浜松、飯塚など）の英語キーを取得
        track_links = await page.query_selector_all("a[href*='/race_info/Program/']")
        track_keys = []
        for link in track_links:
            href = await link.get_attribute("href")
            match = re.search(r'/Program/([^/]+)', href)
            if match: track_keys.append(match.group(1))
        track_keys = list(set(track_keys))

        for key in track_keys:
            # 各場の1Rから12Rまでチェック（ミッドナイトは9Rまでの場合もあるが12回回せば確実）
            for r in range(1, 13):
                url = f"https://autorace.jp/race_info/Program/{key}/{today_str}_{r}/program"
                await page.goto(url)
                
                # 場名取得
                track_tag = await page.query_selector(".race-program__title")
                track_name = (await track_tag.inner_text()).split()[0] if track_tag else key
                
                # 画面上の「投票締切 20:01」という文字をそのまま抜く（計算なし）
                content = await page.content()
                match_time = re.search(r'投票締切\s*(\d{1,2}:\d{2})', content)
                
                if match_time:
                    races.append({
                        "track": track_name,
                        "race_num": f"{r}R",
                        "time": match_time.group(1)
                    })
                else:
                    # そのレースがなければ（例：9Rまでしかない場合）次の場へ
                    if r > 8: break 

    except Exception as e: log(f"オートエラー: {e}")
    return races

async def main():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    all_races = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 競輪（既存）とオート（新規）を合体
        all_races.extend(await fetch_keirin(page))
        all_races.extend(await fetch_auto(page))
        
        await browser.close()

    parsed = []
    seen = set()
    for r in all_races:
        key = f"{r['track']}_{r['race_num']}"
        if key in seen: continue
        try:
            h, m = map(int, r["time"].split(':'))
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            # 日付跨ぎの補正（ミッドナイト対応）
            if dt < now - timedelta(hours=6): dt += timedelta(days=1)
            
            if dt > now:
                parsed.append({
                    "id": key,
                    "track": r["track"],
                    "race_num": r["race_num"],
                    "time_str": r["time"],
                    "deadline": dt.isoformat()
                })
                seen.add(key)
        except: continue

    parsed.sort(key=lambda x: x["deadline"])
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    log(f"--- 保存完了: {len(parsed)} 件 ---")

if __name__ == "__main__":
    asyncio.run(main())
