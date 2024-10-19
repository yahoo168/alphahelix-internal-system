from flask import flash, request, jsonify, render_template, redirect, url_for, flash, send_file
from flask import current_app as app
from flask_login import login_required, current_user

import logging

from datetime import datetime, timedelta, timezone
from bson import ObjectId
from app.utils.google_tools import google_cloud_storage_tools
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import *

from app.utils.alphahelix_database_tools import pool_list_db
#cache在app/__init.py的creat_app中定義，這裡引入cache，避免重複創建
from app import redis_instance
from app import cache
from app import document_edit_perm

from . import main

import logging
logging.basicConfig(level=logging.INFO)

# 取報告的方式類別
## 1. 按照ids（issue review）
## 2. 只給一個id（查看特定文件 or 添加瀏覽紀錄）
## 3  market info（最近100篇，給定doc_type）
## 4. 文件查詢（各種）

def _get_collection_by_doc_type(doc_type, market="US"):
    if (doc_type == "stock_report") and (market == "US"):
        collection = MDB_client["preprocessed_content"]["stock_report"]
    
    elif (doc_type == "stock_report") and (market == "TW"):
        collection = MDB_client["raw_content"]["raw_stock_report_auto"]
    
    elif doc_type == "transcript":
        collection = MDB_client["preprocessed_content"]["event_document"]
    
    elif doc_type == "stock_memo":
        collection = MDB_client["raw_content"]["raw_stock_memo"]
    
    elif doc_type == "industry_report":
        collection = MDB_client["raw_content"]["raw_industry_report"]
        
    else:
        logging.error(f"Invalid doc_type: {doc_type}")
        return None
    
    return collection


def get_stock_document_meta_list(doc_type, ticker=None, market=None, start_timestamp=None, end_timestamp=None, max_num=100):
    # 若沒有market且ticker為None，報錯並退出
    if not ticker and not market:
        logging.error("[Error]: Please specify either ticker or market")
        return []
    
    # 若未提供市場（market），則從資料庫中查找對應的ticker資訊
    if not market and ticker:
        ticker_info = MDB_client["research_admin"]["reference_ticker"].find_one({"ticker": ticker})
        if not ticker_info:
            flash(f"Ticker {ticker} not found in database", "danger")
            return []
        market = ticker_info.get("market")
    
    # 根據市場與文件類型獲取對應的集合
    collection = _get_collection_by_doc_type(doc_type, market)
    
    # 預設查詢條件：未刪除（使用 $ne 是因為部分文檔可能沒有 "is_deleted" 欄位）
    query = {"is_deleted": {"$ne": True}}
    
    # 添加 ticker 條件（如果提供了 ticker）
    if ticker:
        query["tickers"] = ticker
    
    # 添加時間範圍條件
    if start_timestamp or end_timestamp:
        query["data_timestamp"] = {}
        if start_timestamp:
            query["data_timestamp"]["$gte"] = start_timestamp
        if end_timestamp:
            query["data_timestamp"]["$lte"] = end_timestamp
    
    # 執行查詢，按時間戳降序排序並限制最大數量
    try:
        doc_meta_list = list(collection.find(query).sort("data_timestamp", -1).limit(max_num))
    
    except Exception as e:
        logging.error(f"Database query failed: {e}")
        flash("Failed to retrieve documents from the database", "danger")
        return []
    
    # 添加 read_url 到每個文檔元數據中
    for item_meta in doc_meta_list:
        item_meta["doc_type"] = doc_type
        # 文件頁面的url統一到stock_document_page轉址
        item_meta["read_url"] = url_for(
            "main.stock_document_page",
            market=market,
            doc_type=doc_type,
            doc_id=item_meta["_id"]
        )

    return doc_meta_list

# http://127.0.0.1:5000/main/stock_document_search
# 搜尋所有投資文件
@main.route("investment_document_search", methods=['GET', 'POST'])
@login_required
def investment_document_search():
    # 獲取通用的參數
    params = request.form if request.method == 'POST' else request.args
    ticker = params.get("ticker", "").strip()
    start_date = params.get("start_date", "").strip() or None
    end_date = params.get("end_date", "").strip() or None
    recent_days = params.get("recent_days", "").strip() or None
    doc_type = params.get("doc_type", "").strip() or None
    market = params.get("market", "").strip() or None
    
    # 計算時間範圍
    end_timestamp = str2datetime(end_date) if end_date else datetime.now(timezone.utc)
    if recent_days:
        try:
            start_timestamp = end_timestamp - timedelta(days=int(recent_days))
        except ValueError:
            start_timestamp = None
            logging.error(f"Invalid recent_days value: {recent_days}")
    else:
        start_timestamp = str2datetime(start_date) if start_date else None
        
    # 獲取文件元數據
    document_meta_list = []
    if doc_type:
        document_meta_list = get_stock_document_meta_list(
            doc_type=doc_type, ticker=ticker, market=market,
            start_timestamp=start_timestamp, end_timestamp=end_timestamp
        )
    
    # 若未指定文件類型，則依照市場類別查詢預設類型的文件
    # - 美股：Report + Transcript
    # - 台股：Report + Memo
    else:
        stock_report_meta_list = get_stock_document_meta_list(
                doc_type="stock_report", ticker=ticker, market=market,
                start_timestamp=start_timestamp, end_timestamp=end_timestamp
            )
        if market == "US":
            transcript_meta_list = get_stock_document_meta_list(
                doc_type="transcript", ticker=ticker, market=market,
                start_timestamp=start_timestamp, end_timestamp=end_timestamp
            )
            document_meta_list = stock_report_meta_list + transcript_meta_list
            
        elif market == "TW":    
            stock_memo_meta_list = get_stock_document_meta_list(
                doc_type="stock_memo", ticker=ticker, market=market,
                start_timestamp=start_timestamp, end_timestamp=end_timestamp
            )
            document_meta_list = stock_report_meta_list + stock_memo_meta_list

    # 按照時間戳排序，並格式化顯示
    document_meta_list.sort(key=lambda x: x["data_timestamp"], reverse=True)
    for item_meta in document_meta_list:
        item_meta["is_viewed"] = check_document_is_viewed(item_meta, current_user.get_id())
        # 轉換 data_timestamp 為當地時間，保留精度到分鐘
        local_timestamp = pytz.utc.localize(item_meta["data_timestamp"]).astimezone(local_timezone)
        item_meta["data_date_str"] = local_timestamp.strftime('%Y-%m-%d %H:%M')
        # 將data_timestamp統一轉換為精度到分鐘的str（各來源原時間精度不同，在此統一格式化）
        item_meta["data_timestamp"] = item_meta["data_timestamp"].strftime('%Y-%m-%d %H:%M')
        # 若market為空，則為US（部分舊文檔可能缺少這個欄位）
        item_meta["market"] = item_meta.get("market", "US")
    
    return render_template('investment_document_search.html', document_meta_list=document_meta_list)

def add_document_view_record(doc_type, doc_id, user_id, market="US"):
    collection = _get_collection_by_doc_type(doc_type, market)
    
    doc_meta = collection.find_one({"_id": ObjectId(doc_id)})
    if not doc_meta:
        logging.info(f"Stock Document not found: {doc_id}")
        return False
    
    # 若用戶尚未查看過此文件，則更新view_by字段，將當前用戶的id及當前閱讀時間，加入view_by
    is_viewed = check_document_is_viewed(doc_meta, user_id)

    logging.info(f"is_viewed: {is_viewed}")

    if not is_viewed:
        collection.update_one(
            { "_id": ObjectId(doc_id) },
            
            {
                "$addToSet": { 
                    "view_by": { "user_id": ObjectId(user_id), 
                                 "timestamp": datetime.now(timezone.utc) }
                },
            }, upsert=False  # 不需要創建新的文檔，僅更新現有文檔
        )
    return is_viewed
    
@main.route("/stock_document/<market>/<doc_type>/<doc_id>")
@login_required
def stock_document_page(market, doc_type, doc_id):
    collection = _get_collection_by_doc_type(doc_type, market)
    # 根據doc_type取得對應的文檔資訊
    # 若為stock memo，轉址至stock_memo_page（memo格式與report / transcript不同）
    if doc_type == "stock_memo":
        return redirect(url_for('main.stock_memo_page', doc_id=doc_id))
    
    # 若為stock report，則根據market不同，導向不同的頁面    
    elif (doc_type == "stock_report") and (market == "US"):
        html_template = "stock_report_page.html"
    
    elif doc_type == "transcript":
        html_template = "stock_transcript_page.html"
    
    # 若為行業報告或台股個股報告，添加瀏覽紀錄後，直接導向原文連結（因未經過預處理）
    elif (doc_type == "stock_report" and market == "TW") or (doc_type == "industry_report"):    
        doc_meta = collection.find_one({"_id": ObjectId(doc_id)})
        if not doc_meta:
            return render_template('404.html')
        add_document_view_record(doc_type, doc_id, current_user.get_id(), market="TW")
        return redirect(doc_meta["url"])
        
    # 若doc_type不為上述三者，則返回404頁面 
    else:
        return render_template('404.html')

    doc_meta = collection.find_one({"_id": ObjectId(doc_id)})
    add_document_view_record(doc_type, doc_id, current_user.get_id(), market=doc_meta.get("market", "US"))
    # 若物件id對應的文件資料不存在，則返回404頁面
    if not doc_meta:
        return render_template('404.html')
    
    # 個股報告的tickers只有一個，直接取第一位
    doc_meta["ticker"] = doc_meta["tickers"][0]
    doc_meta = beautify_document_for_display(doc_meta)
    
    issue_meta_list, hidden_issue_meta_list = [], []
    for issue_meta in doc_meta.get("issue_summary", []):
        # 將ObjectId轉為str，以便前端綁定於class
        issue_meta["issue_id"] = str(issue_meta["issue_id"])
        # 若issue_content字數大於10（AI可能產生部分無效字串），則判定文件存在該issue相關內容
        if len(issue_meta.get("issue_content", '')) >= 10:
            issue_meta_list.append(issue_meta)
        else:
            hidden_issue_meta_list.append(issue_meta)
    
    return render_template(html_template, 
                        item_meta=doc_meta,
                        issue_meta_list=issue_meta_list,
                        hidden_issue_meta_list=hidden_issue_meta_list)
    
# 個股法說Memo
@main.route("/stock_document/stock_memo/<doc_id>")
@login_required
def stock_memo_page(doc_id):
    item_meta = MDB_client["raw_content"]["raw_stock_memo"].find_one({"_id": ObjectId(doc_id)})
    
    if not item_meta:
        return render_template('404.html')
    
    # 添加文檔查看記錄
    add_document_view_record("stock_memo", doc_id, current_user.get_id(), market="TW")
    
    # 從GCS下載文字文件
    blob = google_cloud_storage_tools.get_blob(bucket_name='investment_report', 
                                               blob_name=item_meta["upload_info"]["blob_name"])

    content = blob.download_as_text(encoding='utf-8')
    content = content.replace("\n", "<br><br>")
    # 格式美化
    item_meta = beautify_document_for_display(item_meta)
    
    context = {
        "ticker": item_meta["tickers"][0],
        "data_date_str": item_meta.get("data_date_str", ''),
        "source": item_meta.get("source", ''),
        "content": content,
    }
    return render_template('stock_memo_page.html', **context)

@main.route("edit_investment_document_metadata", methods=['POST'])
@login_required
@document_edit_perm.require(http_exception=403)
def edit_investment_document_metadata():
    edit_dict = request.get_json()
    doc_type = edit_dict.get("doc_type")
    market = edit_dict.get("market")
    doc_id = edit_dict.get("doc_id")
    title = edit_dict.get("title")
    data_timestamp = datetime.strptime(edit_dict["datetime_str"], '%Y-%m-%d %H:%M') # 日期、時間及微秒
    
    source = edit_dict["data_source"]
    
    new_metadata = {
        "title": title,
        "data_timestamp": data_timestamp,
        "source": source
    }
    try:
        collection = _get_collection_by_doc_type(doc_type, market)
        collection.update_one({"_id": ObjectId(doc_id)}, {"$set": new_metadata})
        return jsonify({'status': 'success', 'message': 'updated seccessfully'})
    
    except Exception as e:
        print(e)
        return jsonify({'status': 'error', 'message': str(e)})

@main.route("delete_investment_document", methods=['POST'])
@login_required
@document_edit_perm.require(http_exception=403)
def delete_investment_document():
    edit_dict = request.get_json()
    doc_type = edit_dict.get("doc_type")
    market = edit_dict.get("market")
    doc_id = edit_dict.get("doc_id")
    
    try:
        collection = _get_collection_by_doc_type(doc_type, market)
        # 設置is_deleted為True，而非直接刪除
        collection.update_one({"_id": ObjectId(doc_id)}, {"$set": {"is_deleted": True}})
        return jsonify({'status': 'success', 'message': 'deleted seccessfully'})
    
    except Exception as e:
        print(e)
        return jsonify({'status': 'error', 'message': str(e)})
    
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