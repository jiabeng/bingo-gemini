from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import collections
import os

app = Flask(__name__)
CORS(app)  # 解決瀏覽器跨域阻擋問題

def fetch_winwin_data():
    """從第三方 API 獲取真實賓果數據"""
    today = datetime.now().strftime('%Y-%m-%d')
    api_url = f"https://winwin.tw/Bingo/GetBingoData?date={today}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": "https://winwin.tw/Bingo",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"API 請求出錯: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/strategy')
def strategy():
    raw_data = fetch_winwin_data()
    
    if not raw_data or len(raw_data) == 0:
        return jsonify({
            "status": "error",
            "message": "無法取得即時數據"
        }), 500

    # 1. 數據清洗
    all_draws = []
    super_numbers = []
    for item in raw_data:
        # BigShowOrder 是開獎號碼字串，例如 "01,02,..."
        nums_str = item.get('BigShowOrder', '')
        if nums_str:
            nums = [int(n) for n in nums_str.split(',')]
            all_draws.append(nums)
            # BullEyeTop 是超級獎號
            super_numbers.append(int(item.get('BullEyeTop', 0)))

    # 2. 熱門與冷門號碼統計
    flat_nums = [n for draw in all_draws for n in draw]
    num_counts = collections.Counter(flat_nums)
    
    # 熱門前 10 名
    hot_nums = [item[0] for item in num_counts.most_common(10)]
    
    # 冷門後 10 名 (從 1-80 中找出出現次數最少的)
    all_possible = set(range(1, 81))
    cold_nums = sorted(list(all_possible), key=lambda x: num_counts[x])[:10]

    # 3. 連號分析 (計算二連號出現頻率)
    pair_counts = collections.Counter()
    for draw in all_draws:
        draw_set = set(draw)
        for n in draw:
            if n + 1 in draw_set:
                pair_counts[(n, n+1)] += 1
    
    # 取前 5 組熱門連號
    hot_pairs = [f"{p[0]}-{p[1]}" for p, count in pair_counts.most_common(5)]

    # 4. 超級獎號尾數分佈 (0-9)
    super_tails = [s % 10 for s in super_numbers]
    tail_freq = collections.Counter(super_tails)
    tail_data = [tail_freq.get(i, 0) for i in range(10)]

    # 5. 職業四星推薦邏輯 (確保 key 名稱與 index.html 完全一致)
    # 策略：取熱門連號第一組 + 熱門號碼補足
    top_pair = pair_counts.most_common(1)[0][0] if pair_counts else (hot_nums[0], hot_nums[1])
    recom_set = set(top_pair)
    for n in hot_nums:
        if len(recom_set) >= 4: break
        recom_set.add(n)
    
    # 最終回傳 JSON
    return jsonify({
        "status": "success",
        "hot_nums": hot_nums,
        "cold_nums": cold_nums,
        "hot_pairs": hot_pairs,
        "tail_distribution": tail_data,
        "four_star_recom": sorted(list(recom_set)), # 這裡必須與 index.html 的 data.four_star_recom 對應
        "sample_size": len(raw_data)
    })

if __name__ == '__main__':
    # 針對 Render 環境自動切換 Port
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
