import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

# 競輪：これまでの成功ロジックをそのまま維持
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
                    # 投票締切の文字が出るまで待機
                    await page.wait_for_selector("text=投票締切", timeout=3000)
                except:
                    if r > 1: break
                    continue
                
                title = await page.title()
                track_name = title.split('｜')[1].replace('オート', '').strip() if '｜' in title else key
                
                body_text = await page.inner_text("body")
                match_time = re.search(r'投票締切\s*(\d{1,2}:\d{2})', body_text)
                
                if match_time:
                    races.append({"track": track_name, "race_
