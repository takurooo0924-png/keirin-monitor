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
    log(f"--- 最終決戦開始: {now.strftime('%H:%M:%S')} ---")
    
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()

        # --- 1. 競輪 (構造無視・距離判定スキャン) ---
        try:
            log("【競輪】Kドリームスへ潜入...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            await page.wait_for_timeout(5000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            for block in soup.find_all(class_="kaisai-list"):
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # ブロック内のテキストをすべて結合
                full_text = block.get_text(separator=' ', strip=True)
                # 「9R」と「23:25」が「100文字以内」にあればペアとみなす（これで1R/9R誤認を防ぐ）
                matches = re.finditer(r'(\d+R)', full_text)
                for m in matches:
                    r_num = m.group(1)
                    # そのレース番号の直後100文字以内にある最初の時刻を探す
                    search_area = full_text[m.end() : m.end() + 100]
                    time_match = re.search(r'(\d{1,2}:\d{2})', search_area)
                    
                    if time_match:
                        t_str = time_match.group(1)
                        # 「結果」という文字が近くにないかチェック
                        if "結果" not in full_text[m.start()-10 : m.end()+20]:
                            races_data.append({"track": track_name, "race_num": r_num, "time_str": t_str})
            log(f"  -> 競輪: {len(races_data)} 件を捕捉")
        except Exception as e:
            log(f"【競輪】エラー: {e}")

        # --- 2. オート (深夜・翌日分も含めて全スキャン) ---
        log("【オート】深夜・翌日分を全スキャン中...")
        try:
            await page.goto("https://www.oddspark.com/autorace/KaisaiYotei.do", timeout=30000)
            await page.wait_for_timeout(3000)
            soup = BeautifulSoup(await page.content(), "html.parser")
            
            # すべての12R予想リンクを取得（ミッドナイト対応）
            links = soup.select('a[href*="Yoso.do"][href*="raceNo=12"]')
            for link in links:
                row = link.find_parent("tr")
                if not row: continue
                row_text = row.get_text()
                track_m = re.search(r'(飯塚|川口|伊勢崎|浜松|山陽)', row_text)
                if not track_m: continue
                
                track_name = track_m.group(1)
                race_url = "https://www.oddspark.com" + link['href']
                
                sub_page = await context.new_page()
                await sub_page.goto(race_url, timeout=20000)
                m = re.search(r'締切時刻\s*(\d{1,2}:\d{2})', await sub_page.content())
                if m:
                    races_data.append({"track": f"{track_name}オート", "race_num": "12R", "time_str": m.group(1)})
                    log(f"    => {track_name} 12R: {m.group(1)} 取得")
                await sub_page.close()
        except Exception as e:
            log(f"【オート】エラー: {e}")

        await browser.close()

    # --- 保存処理 (深夜0時を跨ぐ判定を強化) ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # 現在が夜（18時以降）で、レースが深夜（0時〜5時）なら「翌日」とする
        if now.hour >= 18 and h < 5:
            dt += timedelta(days=1)
        
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"], "race_num": r["race_num"], "time_str": r["time_str"], "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件を保存します ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
