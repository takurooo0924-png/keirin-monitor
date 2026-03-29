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
    log(f"--- 最終検証フェーズ: {now.strftime('%H:%M:%S')} ---")
    
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()

        # --- 1. 競輪 (Kドリームス完全固定・タグ狙い撃ち) ---
        try:
            log("【競輪】Kドリームスをスキャン中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            await page.wait_for_timeout(5000)
            
            # ページ全体のHTMLを取得
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            
            for block in soup.select(".kaisai-list"):
                track_tag = block.select_one(".velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # レース情報の行を特定
                items = block.select("tr, .race-item") # 構造が変わっても対応できるよう複数指定
                for item in items:
                    txt = item.get_text(separator=' ', strip=True)
                    # 「数字R」と「時刻」が同じ行にある場合のみ抽出
                    m = re.search(r'(\d+R).*?(\d{1,2}:\d{2})', txt)
                    if m and "結果" not in txt and "終了" not in txt:
                        races_data.append({"track": track_name, "race_num": m.group(1), "time_str": m.group(2)})
        except Exception as e:
            log(f"【競輪】エラー: {e}")

        # --- 2. オート (飯塚ミッドナイト 23:43 狙い撃ち) ---
        log("【オート】飯塚ミッドナイトを確認中...")
        try:
            # 飯塚12Rの予想ページへダイレクトに飛ぶ
            url = "https://www.oddspark.com/autorace/Yoso.do?raceNo=12&kaisaiBi=20260329&placeCd=31"
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(3000)
            
            txt = await page.content()
            # 「締切時刻 23:43」というパターンをHTML全体から探す
            m = re.search(r'(?:締切時刻|締切)\s*(\d{1,2}:\d{2})', txt)
            if m:
                races_data.append({"track": "飯塚オート", "race_num": "12R", "time_str": m.group(1)})
                log(f"  -> 飯塚 12R: {m.group(1)} を取得成功")
        except Exception as e:
            log(f"【オート】エラー: {e}")

        await browser.close()

    # --- 共通保存処理 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # 深夜0時〜5時のレースなら翌日扱い
        if now.hour >= 18 and h < 5:
            dt += timedelta(days=1)
        
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"], "race_num": r["race_num"], "time_str": r["time_str"], "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件を schedule.json に書き込みます ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)
    log("--- 全工程終了 ---")

if __name__ == "__main__":
    asyncio.run(fetch_data())
