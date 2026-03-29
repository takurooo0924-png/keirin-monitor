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
    log(f"--- 最終精密フェーズ開始: {now.strftime('%H:%M:%S')} ---")
    
    # ミッドナイト対策：深夜（21時以降）なら「明日」の開催もチェック候補に入れる
    check_dates = [now.strftime('%Y-%m-%d')]
    if now.hour >= 21:
        check_dates.append((now + timedelta(days=1)).strftime('%Y-%m-%d'))
    
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()

        # --- 1. 競輪 (精密スキャン：1R/9R誤認を修正) ---
        try:
            log("【競輪】Kドリームスを精密スキャン中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            await page.wait_for_timeout(5000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            for block in soup.find_all(class_="kaisai-list"):
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # 行ごとに解析して、レース番号と時刻のペアを絶対に外さないようにする
                rows = block.find_all("tr")
                for row in rows:
                    row_text = row.get_text(separator=' ', strip=True)
                    # 「9R 23:25」のように、同じ行にあるペアだけを正確に抽出
                    m = re.search(r'(\d+R).*?(\d{1,2}:\d{2})', row_text)
                    if m:
                        r_num, t_str = m.groups()
                        if "結果" not in row_text:
                            races_data.append({"track": track_name, "race_num": r_num, "time_str": t_str})
        except Exception as e:
            log(f"【競輪】エラー: {e}")

        # --- 2. オート (オッズパークからミッドナイトも取得) ---
        log("【オート】ミッドナイト含め取得中...")
        try:
            # 開催予定ページ
            await page.goto("https://www.oddspark.com/autorace/KaisaiYotei.do", timeout=30000)
            await page.wait_for_timeout(3000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            # ページ内のすべての「12R予想」リンク（翌日分も含む）を探す
            links = soup.find_all("a", href=re.compile(r"Yoso.do.*raceNo=12"))
            for link in links:
                # 親要素から競馬場名を探す
                track_text = link.find_parent("tr").get_text()
                track_match = re.search(r'(飯塚|川口|伊勢崎|浜松|山陽)', track_text)
                if track_match:
                    track_name = track_match.group(1)
                    race_url = "https://www.oddspark.com" + link['href']
                    
                    sub_page = await context.new_page()
                    await sub_page.goto(race_url, timeout=20000)
                    sub_soup = BeautifulSoup(await sub_page.content(), "html.parser")
                    
                    # 締切時刻を抽出
                    m = re.search(r'締切時刻\s*(\d{1,2}:\d{2})', sub_soup.get_text())
                    if m:
                        races_data.append({"track": f"{track_name}オート", "race_num": "12R", "time_str": m.group(1)})
                        log(f"    => {track_name} 12R: {m.group(1)} 取得")
                    await sub_page.close()
        except Exception as e:
            log(f"【オート】エラー: {e}")

        await browser.close()

    # --- 保存処理 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        # 時刻が0時〜5時なら「翌日」として扱う
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if h < 5:
            dt += timedelta(days=1)
        
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"], "race_num": r["race_num"], "time_str": r["time_str"], "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件保存 ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
