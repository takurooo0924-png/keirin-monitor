import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

# オートレース場名の漢字変換テーブル
AUTO_TRACK_MAP = {
    "kawaguchi": "川口", "isesaki": "伊勢崎", "hamamatsu": "浜松", "sanyo": "山陽", "iizuka": "飯塚"
}

# 競輪：グレードに関係なく「場名」がある枠のデータをすべて取得する
async def fetch_keirin(page):
    races = []
    try:
        log("【競輪】Kドリームス取得中...")
        await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # 1. ページ内の全テキストと場名の位置を特定する（箱の名前に依存しない）
        # 教えていただいた JS_POST_THROW（G3/G1等）と .velodrome（通常）の両方に対応
        js_code = """
        () => {
            let results = [];
            let trackNodes = document.querySelectorAll('.velodrome, a.JS_POST_THROW');
            trackNodes.forEach(node => {
                let trackName = node.innerText.replace('競輪', '').trim();
                if (!trackName) return;
                
                // 場名を囲っている親の親くらいの大きな枠を自動で見つける
                let container = node.closest('.kaisai-list, .grade-race-list, [class*="list"]') || node.parentElement.parentElement.parentElement;
                results.append({
                    track: trackName,
                    content: container ? container.innerText : ""
                });
            });
            return results;
        }
        """
        # ※ブラウザ側でエラーが出ないよう安全に要素を走査
        blocks = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('.velodrome, a.JS_POST_THROW')).map(node => {
                    let container = node.closest('.kaisai-list, .grade-race-list, div[class*="list"]') || node.parentElement;
                    return { track: node.innerText.replace('競輪', '').trim(), text: container.innerText };
                });
            }
        """)

        for b in blocks:
            track = b['track']
            text = b['text']
            # レース番号と時刻を抽出
            nums = re.findall(r'(\d+)\s*R', text)
            times = re.findall(r'(\d{1,2})\s*[:：]\s*(\d{2})', text)
            
            # 見つかった数だけリストに追加
            if len(nums) > 0 and len(times) > 0:
                # 重複を避けつつ、インデックスの範囲内で取得
                limit = min(len(nums), len(times))
                for i in range(limit):
                    races.append({"track": track, "race_num": nums[i]+"R", "time": f"{times[i][0]}:{times[i][1]}"})
                    
    except Exception as e:
        log(f"競輪エラー: {e}")
    return races

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
            display_name = AUTO_TRACK_MAP.get(key.lower(), key)
            for r in range(1, 13):
                url = f"https://autorace.jp/race_info/Program/{key}/{today_str}_{r}/program"
                await page.goto(url, wait_until="domcontentloaded")
                try: await page.wait_for_selector("text=投票締切", timeout=2000)
                except:
                    if r > 1: break
                    continue
                body_text = await page.inner_text("body")
                match_time = re.search(r'投票締切\s*(\d{1,2}:\d{2})', body_text)
                if match_time:
                    races.append({"track": display_name, "race_num": f"{r}R", "time": match_time.group(1)})
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
            
            # 翌日の早朝開催（ミッドナイト等）への対応
            if dt < now - timedelta(hours=8): dt += timedelta(days=1)
            
            # 【検証用】過去のレースも1時間はJSONに残す（動作確認のため）
            if dt > now - timedelta(hours=1):
                parsed.append({
                    "id": key, "track": r["track"], "race_num": r["race_num"], 
                    "time_str": r["time"], "deadline": dt.isoformat()
                })
                seen.add(key)
        except: continue

    parsed.sort(key=lambda x: x["deadline"])
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    log(f"保存完了: {len(parsed)} 件")

if __name__ == "__main__":
    asyncio.run(main())
