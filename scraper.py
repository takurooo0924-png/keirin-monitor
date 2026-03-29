import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    log(f"--- 全場・最終統合フェーズ開始: {now.strftime('%H:%M:%S')} ---")
    
    date_hyphen = now.strftime('%Y-%m-%d')
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()

        # --- 1. 競輪 (成功済みのロジックを完全維持) ---
        try:
            log("【競輪】Kドリームスへ潜入中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            await page.wait_for_timeout(5000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            blocks = soup.find_all(class_="kaisai-list")
            for block in blocks:
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                full_text = block.get_text(separator=' ', strip=True)
                matches = re.findall(r'(\d+R).*?(\d{1,2}:\d{2})', full_text)
                for r_num, t_str in matches:
                    idx = full_text.find(r_num)
                    if "結果" not in full_text[idx:idx+30]:
                        races_data.append({"track": track_name, "race_num": r_num, "time_str": t_str})
            log(f"  -> 競輪: {len(races_data)} 件の候補を保持")
        except Exception as e:
            log(f"【競輪】エラー: {e}")

        # --- 2. オート (別サイト・裏口ルート) ---
        # ガードの緩いオッズパークの開催一覧をターゲットにします
        log("【オート】別ルート（オッズパーク）から取得中...")
        try:
            await page.goto("https://www.oddspark.com/autorace/KaisaiYotei.do", timeout=30000)
            await page.wait_for_timeout(3000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            # 本日の開催場を探す
            links = soup.find_all("a", href=re.compile(r"KaisaiInfo.do"))
            for link in links:
                track_name = link.get_text(strip=True)
                if track_name:
                    # その場の12Rページへ直接飛ぶ
                    race_url = "https://www.oddspark.com" + link['href'].replace("KaisaiInfo", "Yoso") + "&raceNo=12"
                    log(f"    - {track_name} 12R を確認中...")
                    
                    sub_page = await context.new_page()
                    await sub_page.goto(race_url, timeout=20000)
                    sub_soup = BeautifulSoup(await sub_page.content(), "html.parser")
                    
                    # 「締切時刻 00:00」という文字を探す
                    time_text = sub_soup.get_text()
                    m = re.search(r'締切時刻\s*(\d{1,2}:\d{2})', time_text)
                    if m:
                        races_data.append({"track": f"{track_name}オート", "race_num": "12R", "time_str": m.group(1)})
                        log(f"      => {track_name} 12R: {m.group(1)} 取得成功")
                    await sub_page.close()
        except Exception as e:
            log(f"【オート】別ルートエラー: {e}")

        await browser.close()

    # --- 共通保存処理 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now.hour >= 20 and h < 5: dt += timedelta(days=1)
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"], "race_num": r["race_num"], "time_str": r["time_str"], "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件を schedule.json に保存します ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)
    log("--- 全工程終了 ---")

if __name__ == "__main__":
    asyncio.run(fetch_data())
