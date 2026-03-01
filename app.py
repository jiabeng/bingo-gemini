from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime
import collections
import os

app = Flask(__name__)
CORS(app)

def fetch_winwin_data(target_date=None):
    date_str = target_date if target_date else datetime.now().strftime('%Y-%m-%d')
    api_url = f"https://winwin.tw/Bingo/GetBingoData?date={date_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": "https://winwin.tw/Bingo"
    }
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def get_strategy_recom(history_draws, mode="adaptive"):
    """策略引擎：根據歷史數據產出 4 個建議號碼"""
    if not history_draws: return [1, 2, 3, 4]
    
    all_nums = [n for d in history_draws for n in d]
    counts = collections.Counter(all_nums)
    
    # 激進型：取近 10 期最熱門
    recent_10 = [n for d in history_draws[-10:] for n in d]
    agg_recom = [item[0] for item in collections.Counter(recent_10).most_common(4)]
    
    # 防守型：取今日最冷門（遺漏最久）
    def_recom = sorted(list(range(1, 81)), key=lambda x: counts[x])[:4]
    
    # 自適應：混合熱門與冷門
    if mode == "aggressive": return sorted(agg_recom)
    if mode == "defensive": return sorted(def_recom)
    return sorted(list(set(agg_recom[:2] + def_recom[:2])))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/strategy')
def strategy():
    target_date = request.args.get('date')
    raw_data = fetch_winwin_data(target_date)
    if not raw_data: return jsonify({"status": "error", "message": "數據抓取失敗"}), 500

    # 1. 數據清洗與排序 (由舊到新)
    processed = []
    for item in raw_data:
        processed.append({
            "no": item.get('No'),
            "nums": [int(n) for n in item.get('BigShowOrder', '').split(',')],
            "super": int(item.get('BullEyeTop', 0)),
            "time": item.get('OpenDate').split('T')[1][:5]
        })
    processed.sort(key=lambda x: x['no'])

    # 2. 深度統計分析 (基於全天數據)
    all_draws = [d['nums'] for d in processed]
    flat_nums = [n for d in all_draws for n in d]
    num_counts = collections.Counter(flat_nums)
    
    hot_nums = [item[0] for item in num_counts.most_common(10)]
    cold_nums = sorted(list(range(1, 81)), key=lambda x: num_counts[x])[:10]

    # 連號計算
    pair_counts = collections.Counter()
    for draw in all_draws:
        draw_set = set(draw)
        for n in draw:
            if n + 1 in draw_set: pair_counts[(n, n+1)] += 1
    hot_pairs = [f"{p[0]}-{p[1]}" for p, c in pair_counts.most_common(5)]
    cold_pairs = [f"{i}-{i+1}" for i in range(1, 80) if pair_counts[(i, i+1)] == 0][:5]

    # 超級獎號分析 (尾數預測)
    super_nums = [d['super'] for d in processed]
    tail_counts = collections.Counter([s % 10 for s in super_nums])
    hot_tail = tail_counts.most_common(1)[0][0] if tail_counts else 0
    super_recom = [hot_tail, hot_tail+10, hot_tail+20, hot_tail+30]

    # 3. 實戰回測 PK 邏輯
    comparison_history = []
    win_count = 0
    for i in range(len(processed)):
        curr = processed[i]
        hist_before = [d['nums'] for d in processed[:i]]
        # 模擬「那一期」系統會給出的建議
        sugg = get_strategy_recom(hist_before, "adaptive")
        matches = set(sugg) & set(curr['nums'])
        is_win = len(matches) >= 2
        if is_win: win_count += 1
        
        comparison_history.append({
            "no": curr['no'], "time": curr['time'], "nums": curr['nums'],
            "super": curr['super'], "suggestion": sugg, "match": len(matches), "is_win": is_win
        })

    # 4. 下一期預測
    final_draws = [d['nums'] for d in processed]
    return jsonify({
        "status": "success",
        "hot_nums": hot_nums, "cold_nums": cold_nums,
        "hot_pairs": hot_pairs, "cold_pairs": cold_pairs,
        "super_recom": [n for n in super_recom if 0 < n <= 80],
        "next_recom": {
            "adaptive": get_strategy_recom(final_draws, "adaptive"),
            "aggressive": get_strategy_recom(final_draws, "aggressive"),
            "defensive": get_strategy_recom(final_draws, "defensive")
        },
        "live_win_rate": round((win_count / len(processed)) * 100, 1) if processed else 0,
        "history": comparison_history[::-1][:30] # 取最新 30 期
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
