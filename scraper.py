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

# 競輪場名ホワイトリスト（ゴミデータの混入を完全に遮断）
KEIRIN_TRACKS = [
    "函館", "青森", "いわき平", "弥彦", "前橋", "取手", "宇都宮", "大宮", "西武園", "京王閣", 
    "立川", "松戸", "千葉", "川崎", "平塚", "小田原", "伊東", "静岡", "豊橋", "名古屋", 
    "岐阜", "大垣", "富山", "松阪", "四日市", "福井", "奈良", "向日町", "和歌山", "岸和田", 
    "玉野", "広島", "防府", "高松", "小松島", "高知", "松山", "小倉", "久留米", "武雄", 
    "佐世保", "別府", "熊本"
]

async def fetch_keirin(page):
    races = []
    try:
        log("【競輪】Kドリームス取得中...")
        await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # 場名候補の枠を取得
        blocks = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('.velodrome, a.JS_POST_THROW')).map(node => {
                    let container = node.closest('.kaisai-list, .grade-race-list, div[class*="list"]') || node.parentElement;
                    return { track: node.innerText.replace('競輪', '').trim(), text: container ? container.innerText : "" };
                });
            }
        """)

        seen_keys = set()
        for b in blocks:
            track = b['track']
            if track not in KEIRIN_TRACKS: continue
            
            # 【重要】番号と時刻のズレを防ぐ「セット抽出」ロジック
            # 次の「数字+R」が出てくるまでの範囲内に「時刻」がある場合のみペアとして認める
            # 正規表現: (番号)R ＋ (次の番号Rを含まない任意の文字列) ＋ (時刻)
            pattern = r'(\d+)\s*R(?:(?!\d+\s*R)[\s\S])*?(\d{1,2}[:：]\d{2})'
            matches = re.finditer(pattern, b['text'])
            
            for m in matches:
                race_num = m.group(1) + "R"
                race_time = m.group(2).replace('：', ':')
                key = f"{track}_{race_num}"
                
                if key not in seen_keys:
                    races.append({"track": track, "race_num": race_num, "time": race_time})
                    seen_keys.add(key)
                    
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
            if dt < now - timedelta(hours=8): dt += timedelta(days=1)
            # 締切5分前以降のレースのみを抽出（過去のズレたデータを混入させない）
            if dt > now - timedelta(minutes=5):
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
