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
    "kawaguchi": "川4", "isesaki": "伊勢崎", "hamamatsu": "浜松", "sanyo": "山陽", "iizuka": "飯塚"
}

# 競輪場名ホワイトリスト
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
        
        # ブラウザ内で「テーブルの列」を1つずつ精査する
        js_code = """
        () => {
            let results = [];
            // 各開催場のコンテナ（通常・G3共通）をすべて取得
            let containers = document.querySelectorAll('.kaisai-list, .grade-race-list');
            
            containers.forEach(box => {
                // 場名の特定
                let trackNode = box.querySelector('.velodrome, a.JS_POST_THROW');
                if (!trackNode) return;
                let trackName = trackNode.innerText.replace('競輪', '').trim();
                
                // レーステーブルを取得
                let table = box.querySelector('.kaisai-program_table table');
                if (!table) return;
                
                let ths = table.querySelectorAll('thead th');
                let tds = table.querySelectorAll('tbody td.pre');
                
                // 列（R）ごとにループを回して紐付ける
                for (let i = 0; i < ths.length; i++) {
                    let raceNum = ths[i].innerText.trim(); // "1R" など
                    let cell = tds[i];
                    if (!cell) continue;
                    
                    // ddタグ（締切時間）がある場合のみ抽出（これでゴミとズレを完全排除）
                    let timeNode = cell.querySelector('dd');
                    if (timeNode) {
                        results.push({
                            track: trackName,
                            race_num: raceNum,
                            time: timeNode.innerText.trim()
                        });
                    }
                }
            });
            return results;
        }
        """
        raw_races = await page.evaluate(js_code)
        
        for r in raw_races:
            if r['track'] in KEIRIN_TRACKS:
                races.append(r)
                    
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
            
            # 締切10分前以降のレースのみ採用（直近終わったものも確認できるよう少し余裕を持たせました）
            if dt > now - timedelta(minutes=10):
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
