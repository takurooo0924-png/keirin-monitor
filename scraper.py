import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
import pandas as pd
from bs4 import BeautifulSoup
from io import StringIO
from playwright.async_api import async_playwright

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    today_date = now.strftime('%Y-%m-%d')
    races_data = []
    auto_races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 競輪データ取得
        try:
            page = await browser.new_page()
            await page.goto("https://my.keirin.kdreams.jp/kaisai/?l-id=l-ti-headerTab_tab_raceInfo")
            await page.wait_for_timeout(3000)
            soup_kaisai = BeautifulSoup(await page.content(), "html.parser")
            kaisai_blocks = soup_kaisai.find_all(class_="kaisai-list")
            
            for block in kaisai_blocks:
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                base_track_name = track_tag.text.replace("競輪", "").strip()
                
                times = [""] * 12
                tables = block.find_all("table")
                target_df, fallback_df = None, None
                for tbl in tables:
                    try:
                        df_list = pd.read_html(StringIO(str(tbl)))
                        for df in df_list:
                            if '1R' in df.columns: fallback_df = df
                            has_time = any(re.search(r'\d{1,2}:\d{2}', str(v)) for col in df.columns if re.match(r'^\d+R$', str(col)) for v in df[col])
                            if has_time: target_df = df
                    except: continue
                
                final_df = target_df if target_df is not None else fallback_df
                if final_df is not None:
                    for col in final_df.columns:
                        if isinstance(col, str) and re.match(r'^\d+R$', col):
                            r_idx = int(col.replace('R', '')) - 1
                            if 0 <= r_idx < 12:
                                col_vals = final_df[col].astype(str).tolist()
                                is_ended = any(any(w in v for w in ["映像", "結果", "払戻", "中止"]) for v in col_vals)
                                time_val = ""
                                for v in col_vals:
                                    m = re.search(r'(\d{1,2}:\d{2})', v)
                                    if m:
                                        time_val = m.group(1)
                                        break
                                if not is_ended and time_val:
                                    times[r_idx] = time_val
            races_data.append({"track": base_track_name, "times": times})
            await page.close()
        except Exception as e:
            print(f"競輪データ取得エラー: {e}")

        # オートレースデータ取得
        try:
            page_auto = await browser.new_page()
            tracks_roma = {"川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "飯塚": "iizuka", "山陽": "sanyou"}
            for track_ja, track_roma in tracks_roma.items():
                times_arr = [""] * 12
                is_active = False
                for r in range(12, 0, -1):
                    url = f"https://autorace.jp/race_info/Program/{track_roma}/{today_date}_{r}/program"
                    try:
                        await page_auto.goto(url, wait_until="domcontentloaded", timeout=15000)
                        page_text = await page_auto.evaluate("document.body.innerText")
                        m_time = re.search(r'投票締切\s*(\d{1,2}:\d{2})', page_text)
                        if m_time:
                            is_active = True
                            times_arr[r-1] = m_time.group(1)
                    except: continue
                if is_active:
                    auto_races_data.append({"track": f"{track_ja}オート", "times": times_arr})
            await page_auto.close()
        except Exception as e:
            print(f"オートレースデータ取得エラー: {e}")

        await browser.close()

    # 取得したデータを整えて schedule.json として保存
    parsed_races = []
    for d in (races_data + auto_races_data):
        track_name = d["track"]
        for idx, t_str in enumerate(d["times"]):
            if t_str and t_str != "済":
                h, m = map(int, t_str.split(':'))
                target_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if now.hour >= 20 and h < 5: target_dt += timedelta(days=1)
                elif now.hour < 5 and h >= 20: target_dt -= timedelta(days=1)
                
                if target_dt > now:
                    parsed_races.append({
                        "id": f"{track_name}_{idx+1}R",
                        "track": track_name,
                        "race_num": f"{idx+1}R",
                        "time_str": t_str,
                        "deadline": target_dt.isoformat()
                    })
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_races, f, ensure_ascii=False, indent=2)
    print(f"完了！ {len(parsed_races)}件のレースデータを schedule.json に保存しました。")

if __name__ == "__main__":
    asyncio.run(fetch_data())
