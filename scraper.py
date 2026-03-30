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
    "kawaguchi": "川口",
    "isesaki": "伊勢崎",
    "hamamatsu": "浜松",
    "sanyo": "山陽",
    "iizuka": "飯塚"
}

# 競輪：デザイン無視・全テキスト抽出の完全無条件ロジックに修正
async def fetch_keirin(page):
    races = []
    # 全国43カ所の競輪場リスト（これで画面内のどこに場名があっても確実に見つけます）
    KEIRIN_TRACKS = ["函館", "青森", "いわき平", "弥彦", "前橋", "取手", "宇都宮", "大宮", "西武園", "京王閣", "立川", "松戸", "千葉", "川崎", "平塚", "小田原", "伊東", "静岡", "豊橋", "名古屋", "岐阜", "大垣", "富山", "松阪", "四日市", "福井", "奈良", "向日町", "和歌山", "岸和田", "玉野", "広島", "防府", "高松", "小松島", "高知", "松山", "小倉", "久留米", "武雄", "佐世保", "別府", "熊本"]
    
    try:
        log("【競輪】Kドリームス取得中...")
        await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # 画面に表示されている「すべての文字」を丸ごと取得
        body_text = await page.inner_text("body")
        flat_text = re.sub(r'\s+', ' ', body_text)
        
        # 画面内のどこに競輪場名が書かれているか、その位置をすべて記録
        tracks_found = []
        for t in KEIRIN_TRACKS:
            for match in re.finditer(t, flat_text):
                tracks_found.append((match.start(), t))
        tracks_found.sort(key=lambda x: x[0])
        
        # 1R～12Rの時間表記を無条件ですべて探し出す
        for match in re.finditer(r'(1[0-2]|[1-9])\s*R.{0,30}?(\d{1,2}[:：]\d{2})', flat_text):
            r_pos = match.start()
            r_num = match.group(1)
            r_time = match.group(2).replace('：', ':')
            
            # そのレースの直前に書かれていた競輪場名を割り当てる
            track = None
            for t_pos, t_name in tracks_found:
                if t_pos < r_pos:
                    track = t_name
                else:
                    break
            
            if track:
                races.append({"track": track, "race_num": r_num+"R", "time": r_time})
                
    except Exception as e: 
        log(f"競輪エラー: {e}")
    return races

# オート：公式サイトから「投票締切」を現物抽出し、漢字に変換（※変更なし）
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
            log(f"--- {display_name} ({key}) の番組表を確認 ---")
            
            for r in range(1, 13):
                url = f"https://autorace.jp/race_info/Program/{key}/{today_str}_{r}/program"
                await page.goto(url, wait_until="domcontentloaded")
                try:
                    await page.wait_for_selector("text=投票締切", timeout=3000)
                except:
                    if r > 1: break
                    continue
                
                body_text = await page.inner_text("body")
                match_time = re.search(r'投票締切\s*(\d{1,2}:\d{2})', body_text)
                
                if match_time:
                    races.append({
                        "track": display_name, 
                        "race_num": f"{r}R", 
                        "time": match_time.group(1)
                    })
                    log(f"  {display_name} {r}R: {match_time.group(1)} 取得成功")
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
    log(f"保存完了: {len(parsed)} 件")

if __name__ == "__main__":
    asyncio.run(main())
