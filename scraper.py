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
    log(f"--- 3/30 修正スキャン開始: {now.strftime('%H:%M:%S')} ---")
    
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()

        try:
            log("【競輪】Kドリームスへアクセス中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)
            
            soup = BeautifulSoup(await page.content(), "html.parser")
            blocks = soup.select(".kaisai-list")

            for block in blocks:
                track_tag = block.select_one(".velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # ブロック内の全てのテキストを取得
                full_text = block.get_text(separator=' ', strip=True)
                
                # レース番号(1Rなど)と時刻(00:00)をそれぞれ全部抽出
                r_list = re.findall(r'(\d+R)', full_text)
                t_list = re.findall(r'(\d{1,2}:\d{2})', full_text)
                
                # 番号と時刻の数が一致する場合のみペアにする
                # (Kドリームスの構造上、順番に並んでいるのでこれで正確に取れます)
                if len(r_list) > 0 and len(r_list) == len(t_list):
                    for r_num, t_str in zip(r_list, t_list):
                        # そのレースが「終了」や「結果」でないか周辺をチェック
                        # (簡易的に、テキスト全体からそのレースが過去でないか後ほど時間で判定)
                        races_data.append({"track": track_name, "race_num": r_num, "time_str": t_str})
            
            log(f"  -> 抽出成功: {len(races_data)} 件の候補を発見")

        except Exception as e:
            log(f"【エラー】: {e}")
        await browser.close()

    # --- 未来のレースだけを保存 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        # 3/30 02:30に実行して、10:00のレースを「今日の10:00」と正しく判定
        if dt < now - timedelta(hours=6):
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
