from flask import request, jsonify, render_template, redirect, url_for, flash, send_file
from flask import current_app as app
from flask_login import login_required, current_user

import logging
import pandas as pd
import re

from datetime import datetime, timedelta, timezone
from bson import ObjectId
from app.utils.google_tools import google_cloud_storage_tools, search_investment_gcs_document, search_recent_investment_gcs_document
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import *

from app.utils.alphahelix_database_tools import pool_list_db
#cache在app/__init.py的creat_app中定義，這裡引入cache，避免重複創建
from app import redis_instance
# 引入權限設定
# from app import permissions_dict
from app import research_management_role_perm, us_internal_stock_report_upload_perm, us_market_stock_report_upload_perm, system_edit_perm

from . import main

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@main.route('/')
@main.route("/dashboard")
@login_required
def dashboard():
    return render_template('index.html', title='Dashboard')

@main.route('/get_stock_shorts_summary', methods=['GET'])
def get_stock_shorts_summary():
    ticker, date_str = request.args.get('ticker'), request.args.get('date')
    redis_key = f"stock_news_daily {ticker} {date_str}"
    redis_value = redis_instance.get(redis_key)
    # 若redis中無此日期的新聞，則從mongodb中取得
    if redis_value is None:
        date_datetime = str2datetime(date_str)
        shorts_summary_meta = MDB_client["preprocessed_content"]["shorts_summary"].find_one({"ticker": ticker,
                                                                                             "data_timestamp": date_datetime},
                                                                                            sort=[("data_timestamp", -1)])
        logging.info(shorts_summary_meta)
        if shorts_summary_meta:
            stock_news_daily = shorts_summary_meta.get("content", '')
            
        else:
            stock_news_daily = ''
        # 將新聞存入redis中，並設置過期時間為60秒
        redis_instance.set(redis_key, stock_news_daily, ex=60)
        
    # 若redis中有此日期的新聞，則直接取得（redis中的資料為bytes，需轉為utf-8）
    else:
        logging.info("redis_value is not None")
        stock_news_daily = redis_value.decode('utf-8')
    
    return jsonify({"date": date_str, "stock_news_daily": stock_news_daily})


@main.route("/research_management_overview")
@login_required
@research_management_role_perm.require(http_exception=403)
def research_management_overview():
    ticker_info_meta_list = pool_list_db.get_latest_ticker_info_meta_list()
    id_username_mapping_dict = pool_list_db.get_id_to_username_mapping_dict()
    
    user_id = ObjectId(current_user.get_id())            
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
        # 確保following_users為list（因經過dict轉換，有可能為空字串，導致報錯）
        following_user_meta_list = item_meta.get("following_users", [])
        item_meta["is_following"] = isinstance(following_user_meta_list, list) and (user_id in following_user_meta_list)
        
    return render_template('research_management_overview.html', pool_list_meta_list=ticker_info_meta_list)

@main.route("/update_ticker_following_status", methods=['POST'])
def update_ticker_following_status():
    data = request.json
    item_id, follow_status = data.get('item_id'), data.get('follow_status')
    collection = MDB_client["research_admin"]["ticker_info"]
    user_id = ObjectId(current_user.get_id())
    
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
    internal_stock_report_meta_list = pool_list_db.get_internal_stock_report(ticker=ticker)
    internal_stock_report_meta_list.sort(key=lambda x: x["data_timestamp"], reverse=True)
    id_to_username_mapping_dict = pool_list_db.get_id_to_username_mapping_dict()
    
    for internal_stock_report_meta in internal_stock_report_meta_list:
        internal_stock_report_meta["data_timestamp"] = datetime2str(internal_stock_report_meta["data_timestamp"])
        internal_stock_report_meta["author"] = id_to_username_mapping_dict[internal_stock_report_meta["uploader_id"]].replace("_", " ").title()
        
    context = {
        "ticker": ticker,
        "updated_timestamp": updated_timestamp,
        "profit_rating": profit_rating,
        "risk_rating": risk_rating,
        "investment_thesis": investment_thesis,
        
        "internal_stock_report_meta_list": internal_stock_report_meta_list,
        
    }
    return render_template('ticker_internal_info.html', **context)

@main.route('/ticker_market_info/<ticker>')
@login_required
# @cache.cached(timeout=60)  #緩存60秒
def ticker_market_info(ticker):
    # 初始化變量，避免未定義錯誤
    stock_report_review_date = ''
    bullish_argument_list = []
    bearish_argument_list = []
    bullish_outlook_diff = ''
    bearish_outlook_diff = ''
    stock_info_date = TODAY_DATE_STR
    stock_info_daily = ''
    stock_report_meta_list = []
    issue_meta_list = []
        
    # 取得近期報告的多空觀點彙整（stock_report_review）
    stock_report_review_meta = MDB_client["published_content"]["stock_report_review"].find_one({"ticker": ticker}, sort=[("data_timestamp", -1)])
    if stock_report_review_meta:
        stock_report_review_date = datetime2str(stock_report_review_meta["data_timestamp"])
        stock_report_review = stock_report_review_meta.get("stock_report_review", {})
        bullish_argument_list = stock_report_review.get("bullish_outlook", [])
        bearish_argument_list = stock_report_review.get("bearish_outlook", [])
        bullish_outlook_diff = stock_report_review.get("bullish_outlook_diff", '')
        bearish_outlook_diff = stock_report_review.get("bearish_outlook_diff", '')

    # 取得近期新聞摘要(stock_info_daily)
    shorts_summary_meta = MDB_client["preprocessed_content"]["shorts_summary"].find_one({"ticker": ticker}, sort=[("data_timestamp", -1)])
    if shorts_summary_meta:
        stock_info_date = datetime2str(shorts_summary_meta["data_timestamp"])
        stock_info_daily = shorts_summary_meta.get("shorts_summary", '')

    # 取得近期報告列表（近10篇）
    stock_report_meta_list = list(MDB_client["preprocessed_content"]["stock_report"].find({"ticker": ticker}, sort=[("data_timestamp", -1)], limit=30))
    for stock_report_meta in stock_report_meta_list:
        stock_report_meta["title"] = stock_report_meta["title"].replace("_", " ")[:-4][:80]
        stock_report_meta["data_timestamp"] = datetime2str(stock_report_meta["data_timestamp"])
        stock_report_meta["upload_timestamp"] = datetime2str(stock_report_meta["upload_timestamp"])
        
        source_trans_dict = {"gs": "Goldman Sachs", 
                             "jpm": "J.P. Morgan", 
                             "citi": "Citi", 
                             "barclays": "Barclays",
                             "seeking_alpha": "Seeking Alpha",}
        
        stock_report_meta["source"] = source_trans_dict.get(stock_report_meta["source"], stock_report_meta["source"])
        stock_report_meta["_id"] = str(stock_report_meta["_id"])

    # 取得用戶上傳的追蹤問題列表（近10個）
    issue_id_list = [meta["_id"] for meta in MDB_client["users"]["following_issues"].find({"tickers": ticker}, {"_id": 1}).limit(10)]
    
    for issue_id in issue_id_list:
        issue_meta = MDB_client["published_content"]["issue_review"].find_one({"issue_id": issue_id}, 
                                                                                sort=[("upload_timestamp", -1)])
        if issue_meta:
            issue_meta["data_timestamp"] = datetime2str(issue_meta["data_timestamp"])
            issue_meta["upload_timestamp"] = datetime2str(issue_meta["upload_timestamp"])    
            issue_meta["ref_report_num"] =  len(issue_meta.get("ref_report_id", []))
            issue_meta["added_report_num"] =  len(issue_meta.get("added_report_id", []))
            issue_meta_list.append(issue_meta)
        
    # 在 render_template 中使用 **context 將字典展開為關鍵字參數
    context = {
        'ticker': ticker,
        'stock_report_review_date': stock_report_review_date,
        
        'bullish_argument_list': bullish_argument_list,
        'bearish_argument_list': bearish_argument_list,
        
        'bullish_outlook_diff': bullish_outlook_diff,
        'bearish_outlook_diff': bearish_outlook_diff,
        
        'stock_info_date': stock_info_date,
        'stock_info_daily': stock_info_daily,
        
        'stock_report_meta_list': stock_report_meta_list,
        'item_meta_list': issue_meta_list,
    }
    return render_template('ticker_market_info.html', **context)
         
@main.route('/ticker_setting_info/<ticker>')
# @us_data_view_perm.require(http_exception=403)
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

#http://127.0.0.1:5000/main/report_summary_page/66fbcf6212144cbb9199bd7a
@main.route("/report_summary_page/<report_id>")
@login_required
def report_summary_page(report_id):
    stock_report_meta = MDB_client["preprocessed_content"]["stock_report"].find_one({"_id": ObjectId(report_id)})
    if stock_report_meta:
        # 去除文件的副檔名，如'.pdf'，並進行格式美化：原title有許多'_'，將其拆解後重組
        stock_report_meta["title"] = stock_report_meta["title"].split('.')[0].replace('_', ' ') 
        stock_report_meta["date_str"] = datetime2str(stock_report_meta["data_timestamp"])
        
        issue_meta_list = []
        hidden_issue_meta_list = []
        for issue_meta in stock_report_meta.get("issue_summary", []):
            # 將ObjectId轉為str，以便前端綁定於class
            issue_meta["issue_id"] = str(issue_meta["issue_id"])
            # 若issue_content字數大於10，則將其加入issue_meta_list，否則加入hidden_issue_meta_list
            if len(issue_meta.get("issue_content", '')) >= 10:
                issue_meta_list.append(issue_meta)
            else:
                hidden_issue_meta_list.append(issue_meta)
            
        # 待改：應集中管理，將source縮寫轉換為全名
        source = stock_report_meta["source"]
        
        source_trans_dict = {"gs": "Goldman Sachs", "jpm":"J.P. Morgan", "citi":"Citi", "barclays":"Barclays", "seeking_alpha":"Seeking Alpha"}
        if source in source_trans_dict.keys():
            source = source_trans_dict[source]
        stock_report_meta["source"] = source
        
        return render_template('report_summary_page.html', 
                            item_meta=stock_report_meta,
                            issue_meta_list=issue_meta_list,
                            hidden_issue_meta_list=hidden_issue_meta_list)
    # 若無報告，則返回404頁面
    else:
        return render_template('404.html')

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
        item_meta["followers_num"] = len(item_meta.get("following_users", []))
        
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

@main.route("/investment_assumption_review/<item_id>")
def investment_assumption_review(item_id):
    item_meta_list = list(MDB_client["published_content"]["assumption_review"].find({"assumption_id": ObjectId(item_id)}))
    item_title = ''
    if item_meta_list:
        item_title = item_meta_list[0]["investment_assumption"]
    
    item_meta_list = sorted(item_meta_list, key=lambda x: x['upload_timestamp'], reverse=True)
    for item_meta in item_meta_list:
        item_meta["upload_timestamp"] = datetime2str(item_meta["upload_timestamp"])
    
    # if item_meta_list:
    #     _item_meta_list = [item_meta for _ in range(10)]
    
    context = {
        "item_meta_list": item_meta_list,
        "item_title": item_title,
    }
    
    return render_template("investment_assumption_review.html", **context)

@main.route("/investment_issue_review_records/<item_id>")
def investment_issue_review_records(item_id):
    # 取得issue的基本資訊
    issue_meta = MDB_client["users"]["following_issues"].find_one({"_id": ObjectId(item_id)})
    issue_meta["upload_date_str"] = datetime2str(issue_meta["upload_timestamp"])
    
    # 取得issue_review的meta_list
    issue_review_meta_list = list(MDB_client["published_content"]["issue_review"].find({"issue_id": ObjectId(item_id)}))
    
    issue_review_meta_list = sorted(issue_review_meta_list, key=lambda x: x['upload_timestamp'], reverse=True)
    for item_meta in issue_review_meta_list:
        item_meta["upload_timestamp"] = datetime2str(item_meta["upload_timestamp"])
    
    context = {
        "issue_meta": issue_meta,
        "issue_review_meta_list": issue_review_meta_list,
    }
    return render_template("investment_issue_review_records.html", **context)

@main.route("/investment_issue_review/<item_id>")
def investment_issue_review(item_id):
    # 取得issue的基本資訊
    issue_meta = MDB_client["users"]["following_issues"].find_one({"_id": ObjectId(item_id)})
    issue_meta["upload_date_str"] = datetime2str(issue_meta["upload_timestamp"])
    issue_meta["_id"] = str(issue_meta["_id"])
    
    # 取得issue_review的meta_list
    issue_review_meta = MDB_client["published_content"]["issue_review"].find_one({"issue_id": ObjectId(item_id)}, sort=[("upload_timestamp", -1)])
    if issue_review_meta is not None:
        issue_review_meta["upload_date_str"] = datetime2str(issue_review_meta["upload_timestamp"])
        
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
            item_meta["date_str"] = datetime2str(item_meta["data_timestamp"])
            item_meta["title"] = beautify_report_title(item_meta["title"])
            item_meta["source"] = beautify_broker_name(item_meta["source"])
            
        context = {
            "issue_meta": issue_meta,
            "issue_review_meta": issue_review_meta,
            "added_report_meta_list": added_report_meta_list,
            "other_report_meta_list": other_report_meta_list,
        }
        return render_template("investment_issue_review.html", **context)
    
    # 若無issue_review_meta，則返回404頁面
    else:
        return render_template("404.html")
    
    
@main.route("/ticker_event_overview", methods=['GET', 'POST'])
def ticker_event_overview():
    # Flask 無法自動將 URL 參數傳遞給函數參數中的 ticker_range，需手動從 request.args 中提取 ticker_range
    ticker_range = request.args.get('ticker_range', 'following')  # 將ticker_range從GET參數中獲取，默認為'following'
    
    if request.method == 'POST':
        # 從表單獲取用戶輸入的時間範圍
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        # 將字符串轉換為 datetime 對象
        start_timestamp = str2datetime(start_date_str)
        end_timestamp = str2datetime(end_date_str)
    else:
        # 默認範圍
        start_timestamp = datetime.now(timezone.utc) - timedelta(days=3)
        end_timestamp = datetime.now(timezone.utc) + timedelta(days=30)
    
    event_meta_list = list(MDB_client["research_admin"]["ticker_event"].find({
        "is_deleted": False,
        "event_timestamp": {"$gte": start_timestamp, "$lte": end_timestamp},
    }))
    
    # 透過following_users查找用戶追蹤的ticker，並篩選出相關事件
    if ticker_range == "following":
        following_ticker_meta_list = list(MDB_client["research_admin"]["ticker_info"].find({"following_users": ObjectId(current_user.get_id())}))
        following_ticker_list = [meta["ticker"] for meta in following_ticker_meta_list]
        event_meta_list = [event_meta for event_meta in event_meta_list if event_meta["ticker"] in following_ticker_list]
    print("Hi")
    print(ticker_range)
    for event_meta in event_meta_list:
        event_meta["event_type"] = event_meta["event_type"].replace("_", " ").title()
        event_meta["event_timestamp"] = event_meta["event_timestamp"].strftime('%Y-%m-%d %H:%M')
        
    event_meta_list.sort(key=lambda x: x["event_timestamp"])
    return render_template("ticker_event_overview.html", event_meta_list=event_meta_list)

@main.route("/ticker_news_review", methods=['GET', 'POST'])
def ticker_news_review():
    ticker = request.form.get('ticker')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    start_timestamp = str2datetime(start_date)
    end_timestamp = str2datetime(end_date)
    
    news_meta_list = list(MDB_client["preprocessed_content"]["stock_news_summary"].find({"ticker": ticker, "data_timestamp": {"$gte": start_timestamp, "$lte": end_timestamp}
                                                                                                }, sort=[("data_timestamp", -1)], projection={"_id": 0, "ticker": 1, "data_timestamp": 1, "content": 1}))
    
    for item_meta in news_meta_list:
        item_meta["date"] = datetime2str(item_meta["data_timestamp"])
        
    return render_template("ticker_news_review.html", ticker=ticker, start_date=start_date, end_date=end_date, item_meta_list=news_meta_list)

@main.route("/ticker_news_overviews", methods=['GET', 'POST'])
@login_required
def ticker_news_overviews():
    # 取得用戶的追蹤股票列表
    following_ticker_meta_list = list(MDB_client["research_admin"]["ticker_info"].find({"following_users": ObjectId(current_user.get_id())}))
    following_ticker_list = [meta["ticker"] for meta in following_ticker_meta_list]
    # 取得用戶追蹤股票的新聞摘要
    end_timestamp = datetime.now(timezone.utc)
    start_timestamp = end_timestamp - timedelta(days=14)

    raw_news_meta_list = list(MDB_client["preprocessed_content"]["stock_news_summary"].find({"ticker": {"$in": following_ticker_list}, "data_timestamp": {"$gte": start_timestamp, "$lte": end_timestamp}
                                                                                                }, sort=[("data_timestamp", -1)], projection={"_id": 0, "ticker": 1, "data_timestamp": 1, "content": 1}))
    if len(raw_news_meta_list) > 0:
        # 使用 groupby('data_timestamp') 按照 data_timestamp 进行分组、使用 apply 函数对每个分组创建一个字典，将 ticker 作为键，content 作为值。
        # 使用 to_dict() 方法将结果转换为字典格式。
        news_summary_meta_list = pd.DataFrame(raw_news_meta_list).groupby('data_timestamp').apply(
            lambda group: {
                "data_timestamp": group['data_timestamp'].iloc[0],
                "content": dict(zip(group['ticker'], group['content']))
            }).tolist()

        news_summary_meta_list.sort(key=lambda x: x['data_timestamp'], reverse=True)
        # 計算所有新聞的總字數
        url_pattern = re.compile(r'https?://\S+') # 定義正則表達式來匹配URL
        weekday_list = ['(一)', '(二)', '(三)', '(四)', '(五)', '(六)', '(日)']
        for item_meta in news_summary_meta_list:    
            # 去除 URL 並計算所有新聞的總字數
            word_count = sum(len(url_pattern.sub('', news)) for news in item_meta["content"].values())
            item_meta["read_mins"] = str(round(word_count / 1000, 1)) + " mins"
            # 格式化日期字符串
            date_str = datetime2str(item_meta['data_timestamp'])
            weekday_str = weekday_list[item_meta['data_timestamp'].weekday()]
            # 用於id定位（ticker導引列）
            item_meta["date_str"] = date_str
            # 用於前端顯示（包含星期）
            item_meta["date_with_weekday"] = f"{date_str} {weekday_str}"
        
    # 若無新聞，則返回空列表（避免報錯）
    else:
        news_summary_meta_list = []
        
    return render_template("ticker_news_overviews.html", item_meta_list=news_summary_meta_list)


@main.route('/<page>')
@login_required
def render_static_html(page):
    return render_template(f"{page}.html")

if __name__ == '__main__':
    app.run(debug=True)
    