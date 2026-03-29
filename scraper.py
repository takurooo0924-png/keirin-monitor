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
    log(f"--- 3/30 決戦スキャン開始: {now.strftime('%H:%M:%S')} ---")
    
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
            # ページ全体が読み込まれる（ネットワークが静かになる）までしっかり待つ設定
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(7000) # 念押しで7秒待機
            
            # デバッグ用の写真は引き続き撮り続ける（何かあった時にすぐわかるように）
            await page.screenshot(path="debug_kdreams.png", full_page=True)
            log("  -> 画面撮影完了 (debug_kdreams.png)")

            soup = BeautifulSoup(await page.content(), "html.parser")
            # 会場ごとのブロックを取得
            blocks = soup.select(".kaisai-list")
            log(f"  -> 発見した開催場数: {len(blocks)}")

            for block in blocks:
                track_tag = block.select_one(".velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # 【新ロジック】ブロック内の全テキストから、番号と時間を個別に全抽出
                full_text = block.get_text(separator=' ', strip=True)
                
                r_list = re.findall(r'(\d+R)', full_text)
                t_list = re.findall(r'(\d{1,2}:\d{2})', full_text)
                
                # 番号の数と時間の数が一致する場合のみペアにする
                # (Kドリの表構造上、順番に並んでいるのでこれで正確に取れます)
                if len(r_list) > 0 and len(r_list) == len(t_list):
                    for r_num, t_str in zip(r_list, t_list):
                        # そのレースが「終了」や「結果」でないか周辺をチェック
                        # (簡易的に、テキスト全体からそのレースが過去でないか後ほど時間で判定)
                        races_data.append({"track": track_name, "race_num": r_num, "time_str": t_str})
            
            log(f"  -> 抽出成功: {len(races_data)} 件の候補を発見")

        except Exception as e:
            log(f"【エラー発生】: {e}")
        await browser.close()

    # --- 未来のレースだけを抽出（時間判定を強化） ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        # 深夜実行時、お昼のレースを「昨日のレース（過去）」と判定しないための補正
        # 判定した時間が「今」より1時間以上前なら、それは「今日」ではなく「明日（ミッドナイト等）」
        if dt < now - timedelta(hours=1):
            dt += timedelta(days=1)
        
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"], 
                "race_num": r["race_num"], 
                "time_str": r["time_str"], 
                "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件を保存します ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
