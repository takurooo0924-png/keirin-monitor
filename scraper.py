import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

# 競輪：成功実績のあるコードを維持
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

# オート：公式サイトから「投票締切」の数字をそのまま抽出
async def fetch_auto(page):
    races = []
    try:
        log("【オート】公式サイト取得中...")
        jst = pytz.timezone('Asia/Tokyo')
        today_str = datetime.now(jst).strftime('%Y-%m-%d')
        
        await page.goto("https://autorace.jp/", wait_until="networkidle")
        content = await page.content()
        track_keys = list(set(re.findall(r'/Program/([^/\"\'\s]+)', content)))
        
        if not track_keys:
            await page.goto("https://autorace.jp/netstadium/", wait_until="networkidle")
            content = await page.content()
            track_keys = list(set(re.findall(r'/Program/([^/\"\'\s]+)', content)))

        for key in track_keys:
            log(f"--- {key} の番組表を確認 ---")
            for r in range(1, 13):
                url = f"https://autorace.jp/race_info/Program/{key}/{today_str}_{r}/program"
                await page.goto(url, wait_until="domcontentloaded")
                try:
                    await page.wait_for_selector("text=投票締切", timeout=3000)
                except:
                    if r > 1: break
                    continue
                
                title = await page.title()
                track_name = title.split('｜')[1].replace('オート', '').strip() if '｜' in title else key
                body_text = await page.inner_text("body")
                match_time = re.search(r'投票締切\s*(\d{1,2}:\d{2})', body_text)
                
                if match_time:
                    races.append({"track": track_name, "race_num": f"{r}R", "time": match_time.group(1)})
                    log(f"  {track_name} {r}R: {match_time.group(1)} 取得")
                else:
                    if r > 1: break
    except Exception as e: log(f"オートエラー: {e}")
    return races

async def main():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    all_races = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
        page = await context.new_page()
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
            if dt < now - timedelta(hours=6): dt += timedelta(days=1)
            if dt > now:
                parsed.append({"id": key, "track": r["track"], "race_num": r["race_num"], "time_str": r["time"], "deadline": dt.isoformat()})
                seen.add(key)
        except: continue

    parsed.sort(key=lambda x: x["deadline"])
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    log(f"保存完了: {len(parsed)} 件")

if __name__ == "__main__":
    asyncio.run(main())
