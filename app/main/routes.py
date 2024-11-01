from flask import request, jsonify, render_template, redirect, url_for, flash, send_file
from flask import current_app as app
from flask_login import login_required, current_user

import logging
import pandas as pd
import os, re
import plotly
import plotly.graph_objs as go
import json

from datetime import datetime, timedelta, timezone
from bson import ObjectId
from app.utils.google_tools import google_cloud_storage_tools, search_investment_gcs_document, search_recent_investment_gcs_document
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import *

from app.utils.alphahelix_database_tools import pool_list_db
#cache在app/__init.py的creat_app中定義，這裡引入cache，避免重複創建
from app import redis_instance
# 引入權限設定
from app import portfolio_info_access_role
from app import ticker_setting_perm, issue_setting_perm
from app import cache

from . import main

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@main.route('/')
@main.route("/dashboard")
@login_required
def dashboard():
    return render_template('index.html', title='Dashboard')

@main.route("/coverage_overview")
@login_required
def coverage_overview():
    ticker_info_meta_list = pool_list_db.get_latest_ticker_info_meta_list()
    id_username_mapping_dict = pool_list_db.get_id_to_username_mapping_dict()
    
    # user_id = ObjectId(current_user.get_id())
    # 判斷用戶是否有portfolio_info_access權限（顯示投資組合資訊

    # 待改：判斷用戶是否有portfolio_info_access權限（顯示投資組合資訊）
    has_portfolio_info_access = True
    if ("remote_investment_intern" in current_user.roles) or ("tw_data_subscriber" in current_user.roles):
        has_portfolio_info_access = False
    
    for item_meta in ticker_info_meta_list:
        # 透過user_id查找user_name後，Capitalize the first letter of each word in the username
        researcher_id = item_meta["researchers"].get("researcher_id", '')
        item_meta["researcher_username"] = id_username_mapping_dict.get(researcher_id).replace("_", " ").title()
        # Get the most recent pool_list_status
        item_meta["in_poolList"] = item_meta["poolList_status"].get("in_poolList", False)
        # Extract and format the most recent profit and risk ratings
        item_meta["profit_rating"] = item_meta["investment_ratings"].get("profit_rating", '-').replace("_", " ").title()
        item_meta["risk_rating"] = item_meta["investment_ratings"].get("risk_rating", '-').replace("_", " ").title()
        item_meta["tracking_level"] = item_meta["tracking_status"].get("tracking_level")
    
    # Sort the list by ticker (alphabetically)
    ticker_info_meta_list.sort(key=lambda x: x["ticker"])
    return render_template('coverage_overview.html', 
                           has_portfolio_info_access=has_portfolio_info_access,
                           pool_list_meta_list=ticker_info_meta_list)

@main.route('/internal_investment_report_overview')
def internal_investment_report_overview():
    stock_report_meta_list = pool_list_db.get_internal_stock_report_meta_list()
    for item_meta in stock_report_meta_list:
        item_meta["report_type"] = item_meta["report_type"].title()
        item_meta["title"] = os.path.splitext(item_meta["title"])[0].replace("_", " ")
        
    return render_template('internal_investment_report_overview.html', 
                           stock_report_meta_list=stock_report_meta_list)

@main.route('/ticker_internal_info/<ticker>')
def ticker_internal_info(ticker):
    item_meta = pool_list_db.get_latest_ticker_info_meta_list(ticker_list=[ticker])[0]
    
    updated_timestamp = item_meta.get("investment_ratings", {}).get("updated_timestamp", '')
    if updated_timestamp:
        updated_timestamp = datetime2str(updated_timestamp)
    
    # 取得profit_rating, risk_rating, investment_thesis
    profit_rating = item_meta.get("investment_ratings", {}).get("profit_rating", '').replace("_", " ").title()
    risk_rating = item_meta.get("investment_ratings", {}).get("risk_rating", '').replace("_", " ").title()
    investment_thesis = item_meta.get("investment_ratings", {}).get("investment_thesis", '')
    
    # 取得最近的內部報告
    stock_report_meta_list = pool_list_db.get_internal_stock_report_meta_list(ticker=ticker)
    
    for item_meta in stock_report_meta_list:
        item_meta["report_type"] = item_meta["report_type"].title()
        item_meta["title"] = os.path.splitext(item_meta["title"])[0].replace("_", " ")
        
    context = {
        "ticker": ticker,
        "updated_timestamp": updated_timestamp,
        "profit_rating": profit_rating,
        "risk_rating": risk_rating,
        "investment_thesis": investment_thesis,
        "stock_report_meta_list": stock_report_meta_list,
        
    }
    return render_template('ticker_internal_info.html', **context)

# http://127.0.0.1:5000/main/ticker_market_info_TW/2330_TT
@main.route('/ticker_market_info_TW/<ticker>')
@login_required
def ticker_market_info_TW(ticker):
    # 取得近期報告列表（近N篇）
    stock_report_meta_list = list(MDB_client["raw_content"]["raw_stock_report_auto"].find({"tickers": ticker,
                                                                                           "is_deleted": False}, 
                                                                                          sort=[("data_timestamp", -1)],
                                                                                          limit=100))
    # 券商報告
    for item_meta in stock_report_meta_list:
        item_meta = beautify_document_for_display(item_meta)
        item_meta["read_url"] = url_for("main.stock_document_page", market="TW", doc_type="stock_report", doc_id=item_meta["_id"])
    
    stock_memo_meta_list = list(MDB_client["raw_content"]["raw_stock_memo"].find({"tickers": ticker,
                                                                                  "is_deleted": False}, 
                                                                                 sort=[("data_timestamp", -1)], 
                                                                                 limit=100))
    # 券商法說
    for item_meta in stock_memo_meta_list:
        beautify_document_for_display(item_meta)
        item_meta["title"] = item_meta["beautified_source"] if item_meta["source"] else "Unknown"
        item_meta["read_url"] = url_for("main.stock_document_page", market="TW", doc_type="stock_memo", doc_id=item_meta["_id"])
    
    context = {
        "ticker": ticker,
        "ticker_num": ticker.split("_")[0], #去除台股的後綴
        "stock_report_meta_list": stock_report_meta_list,
        "stock_memo_meta_list": stock_memo_meta_list,
    }
    return render_template('ticker_market_info_TW.html', **context)

# http://127.0.0.1:5000/main/ticker_market_info/AAPL
@main.route('/ticker_market_info/<ticker>')
@login_required
# @cache.cached(timeout=60)  #緩存60秒
def ticker_market_info(ticker):
    # 若ticker為台股，則導向台股頁面（與美股頁面格式不同）
    if ticker.endswith("_TT"):
        return redirect(url_for("main.ticker_market_info_TW", ticker=ticker))
    
    # 取得近期報告列表（近N篇）
    stock_report_meta_list = list(MDB_client["preprocessed_content"]["stock_report"].find({"tickers": ticker}, sort=[("data_timestamp", -1)], limit=100))
    for item_meta in stock_report_meta_list:
        beautify_document_for_display(item_meta)
        # 將文章連結導向內部摘要頁面
        item_meta["read_url"] = url_for("main.stock_document_page", market="US", doc_type="stock_report", doc_id=item_meta["_id"])

    # 取得近期財報會議逐字稿
    event_doc_meta_list = list(MDB_client["preprocessed_content"]["event_document"].find({"tickers": ticker}, sort=[("data_timestamp", -1)], limit=100))
    for item_meta in event_doc_meta_list:
        # 查找文件對應的個股事件，並以事件標題替換原文件標題
        event_id = item_meta.get("event_id")
        event_meta = MDB_client["research_admin"]["ticker_event"].find_one({"_id": event_id})
        item_meta["title"] = event_meta.get("event_title", item_meta["title"])
        beautify_document_for_display(item_meta)
        item_meta["read_url"] = url_for("main.stock_document_page", market="US", doc_type="transcript", doc_id=item_meta["_id"])
        
    context = {
        'ticker': ticker,
        'event_doc_meta_list': event_doc_meta_list,
        'stock_report_meta_list': stock_report_meta_list,
    }
    return render_template('ticker_market_info.html', **context)
         
@main.route('/ticker_setting_info/<ticker>')
@ticker_setting_perm.require(http_exception=403)
def ticker_setting_info(ticker):
    # 取得個股的投資假設
    assumption_meta_list = list(MDB_client["users"]["investment_assumptions"].find({"tickers": ticker}))
    # 建立一個字典來記錄每個 issue 被 linked 的次數
    issue_link_count = {}
    # 計算各個 issue 被多少假設 linked
    for assumption_meta in assumption_meta_list:
        # 將_id轉為str，以便前端綁定於class
        assumption_meta['_id'] = str(assumption_meta["_id"])
        assumption_meta["upload_timestamp"] = datetime2str(assumption_meta.get("upload_timestamp", ''))
        assumption_meta["updated_timestamp"] = datetime2str(assumption_meta.get("updated_timestamp", ''))
        assumption_meta["linked_issue_num"] = len(assumption_meta.get("linked_issues", []))
        
        # 遍歷每個 linked issue 並計算其出現次數
        for linked_issue in assumption_meta.get("linked_issues", []):
            issue_id = linked_issue.get("issue_id")
            if issue_id:
                issue_link_count[issue_id] = issue_link_count.get(issue_id, 0) + 1

    # 取得用戶上傳的追蹤問題列表
    issue_meta_list = list(MDB_client["users"]["following_issues"].find({"tickers": ticker}))
    
    # 更新 issue_meta 中的 linked 次數
    for issue_meta in issue_meta_list:
        issue_meta["upload_timestamp"] = datetime2str(issue_meta.get("upload_timestamp", ''))
        issue_meta["updated_timestamp"] = datetime2str(issue_meta.get("updated_timestamp", ''))
        # 根據 issue_id 更新被 linked 的次數
        issue_meta["linked_by_assumption_num"] = issue_link_count.get(issue_meta['_id'], 0)
        # 將_id轉為str，以便前端綁定於class
        issue_meta['_id'] = str(issue_meta["_id"])

    context = {
        "ticker": ticker,
        "assumption_meta_list": assumption_meta_list,
        "issue_meta_list": issue_meta_list,
    }
    return render_template('ticker_setting_info.html', **context)

@main.route('/issue_search_suggestion', methods=['POST'])
@login_required
def issue_search_suggestion():
    # 取得前端傳來的查詢字串
    query = request.json.get('query')
    # 构建查询条件：在 `issue` 或 `ticker` 字段中查找包含 `query` 的值
    # $regex 运算符： 通过 $regex 运算符在 issue 或 ticker 字段中进行模糊匹配。"$options": "i" 选项使查询不区分大小写
    # 用 $or 运算符来查找 issue 或 ticker 字段中包含 query 的记录
    search_filter = {
        "$or": [
            {"issue": {"$regex": query, "$options": "i"}},  # `i`选项用于不区分大小写的匹配
            {"tickers": {"$regex": query, "$options": "i"}}
        ],
        "is_active": True,
    }
    # 在 MongoDB 中查找符合条件的文档
    results = MDB_client["users"]["following_issues"].find(search_filter)
    # 将结果转换为列表并提取必要的字段
    suggestions = [
        {"issue_id": str(result["_id"]), "issue": result["issue"], "tickers": result.get("tickers", [])}
        for result in results
    ]    
    return jsonify(suggestions)

@main.route('/upload_investment_assumption', methods=['POST'])
@login_required
def upload_investment_assumption():
    assumption, tickers = request.form["assumption"], request.form["tickers"]
    ticker_list = tickers.split(",")
    ticker_list = [ticker.strip() for ticker in ticker_list]
    assumption_meta = {
        "assumption": assumption,
        "tickers": ticker_list,
        "uploader": ObjectId(current_user.get_id()),
        "upload_timestamp": datetime.now(),
        "updated_timestamp": datetime.now(),
        "is_active": True,
        "linked_issues": [],
    }
    MDB_client["users"]["investment_assumptions"].insert_one(assumption_meta)
    flash("Assumption uploaded successfully!", "success")
    return redirect(url_for("main.ticker_setting_info", ticker=ticker_list[0]))

@main.route('/get_assumption_issues', methods=['GET'])
@login_required
def get_assumption_issues():
    assumption_id = request.args.get('assumption_id')
    # 查找对应的 assumption 文档
    assumption_doc = MDB_client["users"]["investment_assumptions"].find_one({"_id": ObjectId(assumption_id)})

    # 获取 linked_issues 字段
    linked_issues = assumption_doc.get('linked_issues', [])

    # 构造响应内容，假设每个 issue 包含 issue_id 和 issue_name
    response_data = []
    for issue_meta in linked_issues:
        if issue_meta:
            response_data.append({
                "issue_id": str(issue_meta["issue_id"]),
                "issue": issue_meta["issue"]
            })

    return jsonify({"status": "success", "linked_issues": response_data})


@main.route('/save_selected_issues', methods=['POST'])
@login_required
def save_selected_issues():
    data = request.json
    assumption_id, linked_issues = data.get('assumption_id'), data.get('linked_issues')
    #  # 将每个 issue_meta 的 issue_id 转换为 ObjectId
    for issue_meta in linked_issues:
        issue_meta["issue_id"] = ObjectId(issue_meta.get("issue_id", ''))
    
    # 获取 MongoDB 集合
    collection = MDB_client["users"]["investment_assumptions"]

    # 查找对应的 assumption 文档，确保它存在
    assumption_doc = collection.find_one({"_id": ObjectId(assumption_id)})

    if not assumption_doc:
        return jsonify({"status": "error", "message": "Assumption not found"}), 404

    # 使用 $set 操作符将 linked_issues 字段替换为当前接收到的值
    collection.update_one(
        {"_id": ObjectId(assumption_id)},
        {"$set": {"linked_issues": linked_issues, "updated_timestamp": datetime.now()}}
    )

    return jsonify({"status": "success"})

@main.route('/upload_issue', methods=['POST'])
@login_required
def upload_issue():
    issue, tickers = request.form["issue"], request.form["tickers"]
    ticker_list = tickers.split(",")
    ticker_list = [ticker.strip() for ticker in ticker_list]
    issue_meta = {
        "issue": issue,
        "tickers": ticker_list,
        "uploader": ObjectId(current_user.get_id()),
        "upload_timestamp": datetime.now(),
        "updated_timestamp": datetime.now(),
        "is_active": False,
    }
    MDB_client["users"]["following_issues"].insert_one(issue_meta)
    flash("Issue uploaded successfully!", "success")
    return redirect(url_for("main.ticker_setting_info", ticker=ticker_list[0]))

@main.route('/update_assumption_status', methods=['POST'])
def update_assumption_status():
    data = request.json
    assumption_id, is_active = data.get('assumption_id'), data.get('is_active')
    # 更新issue的狀態(is_active: True/False)
    MDB_client["users"]["investment_assumptions"].update_one({"_id": ObjectId(assumption_id)}, {"$set": {"is_active": is_active,
                                                                                              "updated_timestamp:": datetime.now()}})
    return jsonify({"status": "success"})

@main.route('/update_issue_status', methods=['POST'])
def update_issue_status():
    data = request.json
    issue_id, is_active = data.get('issue_id'), data.get('is_active')
    # 更新issue的狀態(is_active: True/False)
    MDB_client["users"]["following_issues"].update_one({"_id": ObjectId(issue_id)}, {"$set": {"is_active": is_active,
                                                                                              "updated_timestamp:": datetime.now()}})
    return jsonify({"status": "success"})

# 顯示following_issues以及investment_assumptions的總覽表格（以及追蹤按鈕）
@main.route("/investment_tracking_overview/<tracking_type>")
def investment_tracking_overview(tracking_type):
    # 製作username與employee_id的對應表
    user_id = current_user.get_id()
    user_info_meta_list = list(MDB_client["users"]["user_basic_info"].find())
    mapping_df = pd.DataFrame(user_info_meta_list).loc[:, ["username", "_id"]].set_index("_id")
    id_mapping_dict = mapping_df.to_dict(orient='index')
    
    if tracking_type == "following_issues":
        collection = MDB_client["users"]["following_issues"]
        content_field_name = "issue"
        html_template = 'investment_issue_overview.html'
        
    elif tracking_type == "investment_assumptions":
        collection = MDB_client["users"]["investment_assumptions"]
        content_field_name = "assumption"
        html_template = 'investment_assumption_overview.html'
    
    # 取得所有active的item_meta_list
    item_meta_list = list(collection.find({"is_active": True}))
    for item_meta in item_meta_list:
        item_meta["upload_timestamp"] = datetime2str(item_meta["upload_timestamp"])
        item_meta["updated_timestamp"] = datetime2str(item_meta["updated_timestamp"])
        item_meta["item_name"] = item_meta[content_field_name]
        item_meta["item_type"] = tracking_type
        item_meta["uploader"] = id_mapping_dict[item_meta["uploader"]]["username"]
        item_meta["is_following"] = (ObjectId(user_id) in item_meta.get("following_users", []))
        
    return render_template(html_template, item_meta_list=item_meta_list)

# 追蹤/取消追蹤特定的投資主題（包含investment_assumptions以及）
@main.route("/update_investment_tracking_status/<tracking_type>", methods=['POST'])
def update_investment_tracking_status(tracking_type):
    data = request.json
    item_id = data.get('item_id')
    follow_status = data.get('follow_status')
    user_id = current_user.get_id()
    
    if tracking_type == "following_issues":
        collection = MDB_client["users"]["following_issues"]
    elif tracking_type == "investment_assumptions":
        collection = MDB_client["users"]["investment_assumptions"]
        
    if follow_status:
        # 如果 follow_status 为 True，添加 user_id 到 following_users
        collection.update_one(
            {"_id": ObjectId(item_id)},
            {"$addToSet": {"following_users": ObjectId(user_id)}}  # 使用 $addToSet 防止重复添加
        )
    else:
        # 如果 follow_status 为 False，从 following_users 中移除 user_id
        collection.update_one(
            {"_id": ObjectId(item_id)},
            {"$pull": {"following_users": ObjectId(user_id)}}  # 使用 $pull 移除 user_id
        )

    return jsonify({"status": "success"})

# 待改：改為歷史紀錄
@main.route("/investment_assumption_review_records/<item_id>")
def investment_assumption_review_records(item_id):
    item_meta_list = list(MDB_client["published_content"]["assumption_review"].find({"assumption_id": ObjectId(item_id)}))
    item_title = ''
    if item_meta_list:
        item_title = item_meta_list[0]["investment_assumption"]
    
    item_meta_list = sorted(item_meta_list, key=lambda x: x['upload_timestamp'], reverse=True)
    for item_meta in item_meta_list:
        item_meta["upload_timestamp"] = datetime2str(item_meta["upload_timestamp"])
    
    context = {
        "item_meta_list": item_meta_list,
        "item_title": item_title,
    }
    
    return render_template("investment_assumption_review_records.html", **context)

@main.route("/investment_assumption_review/<item_id>")
def investment_assumption_review(item_id):
    assumption_meta = MDB_client["users"]["investment_assumptions"].find_one({"_id": ObjectId(item_id)})
    
    review_meta_list = list(MDB_client["published_content"]["assumption_review"].find({"assumption_id": ObjectId(item_id)}, 
                                                                                          sort=[("data_timestamp", -1)]))
    
    for item_meta in review_meta_list:
        item_meta["data_date_str"] = datetime2str(item_meta["data_timestamp"])
        
    review_meta = review_meta_list[0]
    
    # 模擬的數據
    risk_score_raw_data = [{"date": item_meta["data_date_str"], "score": item_meta["risk_score"]} for item_meta in review_meta_list]
    risk_score_df = pd.DataFrame(risk_score_raw_data)
    #df['date'] = pd.to_datetime(df['date']).dt.date  # 去除時間，只保留日期部分
    
    # 使用 Plotly 創建圖表
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=risk_score_df['date'],
        y=risk_score_df['score'],
        mode='lines+markers',
        name='Score'
    ))
    fig.update_layout(
        # title='Risk Score',
        xaxis_title='Data',
        yaxis_title='Score',
        # xaxis=dict(
        #     tickformat='%Y-%m-%d'  # 設置日期格式
        # )
    )

    # 將圖表轉換為 JSON 格式，傳遞到前端
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    context = {
        "assumption_meta": assumption_meta,
        "review_meta": review_meta,
        "graphJSON": graphJSON,
    }
    
    return render_template("investment_assumption_review.html", **context)


@main.route("/investment_issue_review/<item_id>")
def investment_issue_review(item_id):
    # 取得issue的基本資訊
    issue_meta = MDB_client["users"]["following_issues"].find_one({"_id": ObjectId(item_id)})
    # 若該issue不存在，則返回404頁面    
    if issue_meta is None:
        return render_template("404.html")
    
    issue_meta["upload_date_str"] = datetime2str(issue_meta["upload_timestamp"])
    issue_meta["_id"] = str(issue_meta["_id"])
    
    # 取得issue_review的meta_list
    issue_review_meta = MDB_client["published_content"]["issue_review"].find_one({"issue_id": ObjectId(item_id)}, sort=[("upload_timestamp", -1)])
    
    if issue_review_meta is not None:
        issue_review_meta["data_date_str"] = datetime2str(issue_review_meta["data_timestamp"])
        # 取得參考報告列表
        ref_report_id_list = issue_review_meta.get("ref_report_id", [])
        added_report_id_list = issue_review_meta.get("added_report_id", [])
        other_report_id_list = list(set(ref_report_id_list) - set(added_report_id_list))
        
        # 依據id取得報告的meta_list後，進行排序
        added_report_meta_list = list(MDB_client["preprocessed_content"]["stock_report"].find({"_id": {"$in": added_report_id_list}}))
        added_report_meta_list.sort(key=lambda x: x["data_timestamp"], reverse=True)
        other_report_meta_list = list(MDB_client["preprocessed_content"]["stock_report"].find({"_id": {"$in": other_report_id_list}}))
        other_report_meta_list.sort(key=lambda x: x["data_timestamp"], reverse=True)
        
        # 格式美化
        for item_meta in added_report_meta_list + other_report_meta_list:
            item_meta = beautify_document_for_display(item_meta)
            item_meta["read_url"] = url_for("main.stock_document_page", market="US", doc_type="stock_report", doc_id=item_meta["_id"])
            
    else:
        issue_review_meta = {}
        added_report_meta_list = []
        other_report_meta_list = []
        
    context = {
        "issue_meta": issue_meta,
        "issue_review_meta": issue_review_meta,
        "added_report_meta_list": added_report_meta_list,
        "other_report_meta_list": other_report_meta_list,
    }
    return render_template("investment_issue_review.html", **context)

@main.route("/investment_issue_review_records/<item_id>")
def investment_issue_review_records(item_id):
    # 取得issue的基本資訊
    issue_meta = MDB_client["users"]["following_issues"].find_one({"_id": ObjectId(item_id)})
    issue_meta["upload_date_str"] = datetime2str(issue_meta["upload_timestamp"])
    
    # 取得issue_review的meta_list
    issue_review_meta_list = list(MDB_client["published_content"]["issue_review"].find({"issue_id": ObjectId(item_id)}))
    issue_meta["review_num"] = len(issue_review_meta_list)
    issue_review_meta_list = sorted(issue_review_meta_list, key=lambda x: x['data_timestamp'], reverse=True)
    for item_meta in issue_review_meta_list:
        item_meta["data_date_str"] = datetime2str(item_meta["data_timestamp"])
        
    context = {
        "issue_meta": issue_meta,
        "issue_review_meta_list": issue_review_meta_list,
    }
    return render_template("investment_issue_review_records.html", **context)

# IPhone在新興市場（中國、印度...）的銷售情況
@main.route("/investment_issue_setting/<item_id>", methods=['POST'])
@issue_setting_perm.require(http_exception=403)
def investment_issue_setting(item_id):
    try:
        # 從 POST 請求中獲取 JSON 數據
        data = request.get_json()
        issue = data.get('issue')
        tickers = data.get('tickers') #在前端已經進行過處理，將tickers以逗號分隔後轉為list傳遞
        if len(tickers) > 5:
            raise ValueError("The number of tickers should not exceed 5.")
        
        # 更新issue的資訊
        MDB_client["users"]["following_issues"].update_one({"_id": ObjectId(item_id)}, 
                                                           {"$set": {"issue": issue, "tickers": tickers}})
        
        # 返回成功回應
        #return redirect(url_for("main.investment_issue_review", item_id=item_id))
        return jsonify({'status': 'success', 'message': 'Issue updated successfully!'})

    except Exception as e:
        # 如果出現錯誤，返回錯誤信息
        return jsonify({'status': 'error', 'message': str(e)}), 400

@main.route("/ticker_event_overview", methods=['GET', 'POST'])
def ticker_event_overview():
    # Flask 無法自動將 URL 參數傳遞給函數參數中的 ticker_range，需手動從 request.args 中提取 ticker_range
    ticker_range = request.args.get('ticker_range', 'all')  # 將ticker_range從GET參數中獲取，默認為'all'
    
    # 默認模式：查詢最近3天至未來30天的事件
    if request.method == 'GET':
        start_timestamp = datetime.now(timezone.utc) - timedelta(days=3)
        end_timestamp = datetime.now(timezone.utc) + timedelta(days=30)
        event_meta_list = pool_list_db.get_ticker_event_meta_list(start_timestamp=start_timestamp, end_timestamp=end_timestamp)
        
        # 查找用戶追蹤的ticker，並篩選出相關事件
        if ticker_range == "following":
            following_ticker_list = pool_list_db.get_following_ticker_list(user_id=ObjectId(current_user.get_id()))
            event_meta_list = [event_meta for event_meta in event_meta_list if event_meta["ticker"] in following_ticker_list]
    
    # 查詢模式：從表單獲取用戶輸入的時間範圍，將字符串轉換為 datetime 對象
    elif request.method == 'POST':
        start_date_str, end_date_str = request.form.get('start_date'), request.form.get('end_date')
        ticker = request.form.get('ticker')
        # 判斷用戶的查詢條件是否為空，若為空則將其設置為None
        start_timestamp = str2datetime(start_date_str) if start_date_str else None
        end_timestamp = str2datetime(end_date_str) if end_date_str else None
        ticker_list = [ticker] if ticker else None
        
        event_meta_list = pool_list_db.get_ticker_event_meta_list(start_timestamp=start_timestamp, end_timestamp=end_timestamp, ticker_list=ticker_list)
    
    for item_meta in event_meta_list:
        item_meta["linked_document_num"] = len(item_meta.get("linked_documents", []))
        # 判斷事件是已經發生 / 即將發生（可能有誤差，因此處以UTC時間為準，但收錄時可能包含各種時區）
        item_meta["is_upcoming"] = item_meta["event_timestamp"].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        
    return render_template("ticker_event_overview.html", event_meta_list=event_meta_list)

@main.route('/<page>')
@login_required
def render_static_html(page):
    return render_template(f"{page}.html")

if __name__ == '__main__':
    app.run(debug=True)