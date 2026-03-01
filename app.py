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
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://winwin.tw/Bingo"}
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def get_suggestions(history_draws, mode="adaptive"):
    """
    策略引擎：
    - aggressive: 專抓近5期最熱門
    - defensive: 專抓長期未出號碼 (冷門)
    - adaptive: 根據前一期勝率自動切換
    """
    if not history_draws: return [1, 2, 3, 4]
    
    all_nums = [n for d in history_draws for n in d]
    counts = collections.Counter(all_nums)
    
    # 激進型：近5期熱門
    recent_5 = [n for d in history_draws[-5:] for n in d]
    aggressive_recom = [item[0] for item in collections.Counter(recent_5).most_common(4)]
    
    # 防守型：從1-80選出出現次數最少的
    defensive_recom = sorted(list(range(1, 81)), key=lambda x: counts[x])[:4]
    
    # 自適應：檢查上一期誰準就用誰
    if mode == "aggressive": return sorted(aggressive_recom)
    if mode == "defensive": return sorted(defensive_recom)
    
    # 預設自適應邏輯 (簡單示範：混合型)
    return sorted(list(set(aggressive_recom[:2] + defensive_recom[:2])))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/strategy')
def strategy():
    target_date = request.args.get('date')
    raw_data = fetch_winwin_data(target_date)
    if not raw_data: return jsonify({"status": "error"}), 500

    # 1. 數據清洗 (舊 -> 新)
    processed = []
    for item in raw_data:
        processed.append({
            "no": item.get('No'),
            "nums": [int(n) for n in item.get('BigShowOrder', '').split(',')],
            "super": int(item.get('BullEyeTop', 0)),
            "time": item.get('OpenDate').split('T')[1][:5]
        })
    processed.reverse()

    # 2. 模擬實戰回測 (PK 看板)
    comparison_history = []
    win_count = 0
    
    # 用來存放每一期「當下」產出的建議
    for i in range(len(processed)):
        current_draw = processed[i]
        # 獲取「此期之前」的所有資料來做預測
        history_so_far = [d['nums'] for d in processed[:i]]
        
        # 取得上一期建議 (模擬玩家在當下看到的號碼)
        suggestion = get_suggestions(history_so_far)
        
        # 比對結果
        matches = set(suggestion) & set(current_draw['nums'])
        match_count = len(matches)
        is_win = match_count >= 2 # 四星中2星即有獎
        if is_win: win_count += 1
        
        comparison_history.append({
            "no": current_draw['no'],
            "time": current_draw['time'],
            "nums": current_draw['nums'],
            "super": current_draw['super'],
            "suggestion": suggestion,
            "match": match_count,
            "is_win": is_win
        })

    # 3. 生成「下一期」預測 (給前端顯示)
    final_history_nums = [d['nums'] for d in processed]
    next_recom = {
        "aggressive": get_suggestions(final_history_nums, "aggressive"),
        "defensive": get_suggestions(final_history_nums, "defensive"),
        "adaptive": get_suggestions(final_history_nums, "adaptive")
    }

    return jsonify({
        "status": "success",
        "next_recom": next_recom,
        "live_win_rate": round((win_count / len(processed)) * 100, 1) if processed else 0,
        "history": comparison_history[::-1], # 回傳最新在前的紀錄
        "sample_size": len(processed)
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
