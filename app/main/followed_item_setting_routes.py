from flask import request, jsonify, render_template, url_for, redirect, flash
from flask import current_app as app

from flask_login import login_required, current_user
from bson import ObjectId
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import *

from . import main

@main.route('/ticker_following_setting')
@login_required
def ticker_following_setting():
    following_ticker_list = MDB_client["users"]["user_basic_info"].find_one(
        {"_id": ObjectId(current_user.get_id())}, {"followed_tickers": 1,}).get("followed_tickers", [])
    
    # 將ticker分類為TW/US
    TW_following_ticker_list, US_following_ticker_list = [], []
     
    for ticker in following_ticker_list:
        if ticker.endswith('_TT'):
            TW_following_ticker_list.append(ticker)
        else:
            US_following_ticker_list.append(ticker)
            
    # 將ticker分類為TW/US
    context = {
        "TW_following_ticker_list": sorted(TW_following_ticker_list),
        "US_following_ticker_list": sorted(US_following_ticker_list),
    }
    return render_template('ticker_following_setting.html', **context)

@main.route('/follow_ticker/<ticker>', methods=['GET'])
def follow_ticker(ticker):
    if not ticker:
        return jsonify({"error": "Missing ticker"}), 400
    
    MDB_client["users"]["user_basic_info"].update_one(
        {"_id": ObjectId(current_user.get_id())},
        {"$addToSet": {"followed_tickers": ticker}}
    )
    
    # 通知訊息
    flash(f"「{ticker}」追蹤成功 !", "success")
    return redirect(url_for('main.ticker_following_setting'))

@main.route('/cancel_follow_ticker', methods=['POST'])
def cancel_follow_ticker():
    ticker = request.get_json().get('ticker')
    if not ticker:
        return jsonify({"error": "Missing ticker"}), 400
    
    MDB_client["users"]["user_basic_info"].update_one(
        {"_id": ObjectId(current_user.get_id())},
        {"$pull": {"followed_tickers": ticker}}
    )
    
    return jsonify({"message": f"{ticker}"})

# Auto complete: Ticker Search
@main.route('/ticker_search_suggestion', methods=['GET'])
def ticker_search_suggestion():
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify([])
    
    # Search MongoDB for tickers and company names matching the query
    search_results = MDB_client["research_admin"]["reference_ticker"].find({
        "$or": [
            {"ticker": {"$regex": f"^{query}", "$options": "i"}},  # 強制從開頭匹配
            {"company_name": {"$regex": f"^{query}", "$options": "i"}}  # 強制從開頭匹配
        ]
    }, {"ticker": 1, "company_name": 1, "_id": 0}).limit(10)

    # Extract tickers and company names from the search results
    results = [{"ticker": result["ticker"], "company_name": result.get("company_name", "")} for result in search_results]
    
    return jsonify(results)