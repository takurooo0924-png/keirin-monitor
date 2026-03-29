import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

# 競輪：成功実績のあるコードを完全に維持
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

# オートレース：公式サイトから「投票締切」を現物抽出
async def fetch_auto(page):
    races = []
    try:
        log("【オート】公式サイト取得中...")
        jst = pytz.timezone('Asia/Tokyo')
        today_str = datetime.now(jst).strftime('%Y-%m-%d')
        
        # 1. 開催場を特定（トップページからリンクを全スキャン）
        await page.goto("https://autorace.jp/", wait_until="networkidle")
        content = await page.content()
        track_keys = list(set(re.findall(r'/Program/([^/\"\'\s]+)', content)))
        
        if not track_keys:
            log("場名が見つかりません。ネットスタジアム側を確認します。")
            await page.goto("https://autorace.jp/netstadium/", wait_until="networkidle")
            content = await page.content()
            track_keys = list(set(re.findall(r'/Program/([^/\"\'\s]+)', content)))

        for key in track_keys:
            log(f"--- {key} の番組表をスキャン ---")
            # 1Rから順に確認
            for r in range(1, 13):
                url = f"https://autorace.jp/race_info/Program/{key}/{today_str}_{r}/program"
                await page.goto(url, wait_until="domcontentloaded")
                
                # 「投票締切」という文字が出るまで最大5秒待機（遅延対策）
                try:
                    await page.wait_for_selector("text=投票締切", timeout=5000)
                except:
                    # 見つからなければ、そのレース（または場）は
