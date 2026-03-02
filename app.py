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
    if not history_draws: return [1, 2, 3, 4]
    all_nums = [n for d in history_draws for n in d]
    counts = collections.Counter(all_nums)
    recent_10 = [n for d in history_draws[-10:] for n in d]
    agg_recom = [item[0] for item in collections.Counter(recent_10).most_common(4)]
    def_recom = sorted(list(range(1, 81)), key=lambda x: counts[x])[:4]
    
    if mode == "aggressive": return sorted(agg_recom)
    if mode == "defensive": return sorted(def_recom)
    return sorted(list(set(agg_recom[:2] + def_recom[:2])))[:4]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/strategy')
def strategy():
    target_date = request.args.get('date')
    raw_data = fetch_winwin_data(target_date)
    if not raw_data: return jsonify({"status": "error", "message": "API 無法獲取數據"}), 500

    processed = []
    for item in raw_data:
        processed.append({
            "no": item.get('No'),
            "nums": [int(n) for n in item.get('BigShowOrder', '').split(',')],
            "super": int(item.get('BullEyeTop', 0)),
            "time": item.get('OpenDate').split('T')[1][:5]
        })
    processed.sort(key=lambda x: x['no'])

    # 1. 深度分析：連開與遺漏
    streaks = {i: {"hit": 0, "miss": 0} for i in range(1, 81)}
    for i in range(1, 81):
        for d in reversed(processed):
            if i in d['nums']:
                if streaks[i]['miss'] == 0: streaks[i]['hit'] += 1
                else: break
            else:
                if streaks[i]['hit'] == 0: streaks[i]['miss'] += 1
                else: break

    hot_streaks = [{"num": k, "val": v['hit']} for k, v in streaks.items() if v['hit'] >= 2]
    cold_streaks = [{"num": k, "val": v['miss']} for k, v in streaks.items() if v['miss'] >= 5]

    # 2. 連號遺漏與黃金組合
    pair_streaks = {}
    for n in range(1, 80):
        miss = 0
        for d in reversed(processed):
            if n in d['nums'] and n+1 in d['nums']: break
            miss += 1
        if miss >= 5: pair_streaks[f"{n}-{n+1}"] = miss

    correlations = collections.Counter()
    for d in processed:
        draw_list = sorted(d['nums'])
        for i in range(len(draw_list)):
            for j in range(i + 1, len(draw_list)):
                correlations[(draw_list[i], draw_list[j])] += 1
    
    top_corr = [{"pair": f"{p[0]}, {p[1]}", "count": c} for p, c in correlations.most_common(5)]

    # 3. 超級獎號與四星推薦
    super_nums = [d['super'] for d in processed]
    tail_counts = collections.Counter([s % 10 for s in super_nums])
    hot_tail = tail_counts.most_common(1)[0][0] if tail_counts else 0
    super_recom = [str(n).zfill(2) for n in [hot_tail, hot_tail+10, hot_tail+20, hot_tail+30] if 0 < n <= 80]

    # 4. 回測 PK 邏輯
    comparison_history = []
    win_count = 0
    for i in range(len(processed)):
        curr = processed[i]
        hist_before = [d['nums'] for d in processed[:i]]
        sugg = get_strategy_recom(hist_before, "adaptive")
        matches = set(sugg) & set(curr['nums'])
        is_win = len(matches) >= 2
        if is_win: win_count += 1
        comparison_history.append({
            "no": curr['no'], "time": curr['time'], "nums": curr['nums'],
            "super": curr['super'], "suggestion": [str(x).zfill(2) for x in sugg], 
            "match": len(matches), "is_win": is_win
        })

    final_draws = [d['nums'] for d in processed]
    return jsonify({
        "status": "success",
        "hot_streaks": sorted(hot_streaks, key=lambda x: x['val'], reverse=True)[:10],
        "cold_streaks": sorted(cold_streaks, key=lambda x: x['val'], reverse=True)[:10],
        "pair_missing": dict(sorted(pair_streaks.items(), key=lambda x: x[1], reverse=True)[:8]),
        "correlations": top_corr,
        "super_recom": super_recom,
        "next_recom": {
            "adaptive": [str(x).zfill(2) for x in get_strategy_recom(final_draws, "adaptive")],
            "aggressive": [str(x).zfill(2) for x in get_strategy_recom(final_draws, "aggressive")],
            "defensive": [str(x).zfill(2) for x in get_strategy_recom(final_draws, "defensive")]
        },
        "live_win_rate": round((win_count / len(processed)) * 100, 1) if processed else 0,
        "history": comparison_history[::-1][:30]
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
