from flask import request, jsonify, render_template, redirect, url_for, flash, send_file, session, g
from flask import current_app as app
from flask_login import login_required, current_user

from collections import Counter
import os, io, logging
import pandas as pd

from datetime import datetime, timedelta
from bson import ObjectId

from app.utils.readwise_tools import readwise_client
from app.utils.google_tools import google_cloud_storage_tools, search_investment_gcs_document, search_recent_investment_gcs_document
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import TODAY_DATE_STR, datetime2str, str2datetime, unix_timestamp2datetime, is_valid_report_name, convert_objectid_to_str

from app.utils.alphahelix_database_tools import pool_list_db
#cache在app/__init.py的creat_app中定義，這裡引入cache，避免重複創建
from app import cache, redis_instance
# 引入權限設定
from app import us_data_view_perm, us_data_upload_perm, us_data_edit_perm, tw_data_view_perm, tw_data_upload_perm, tw_data_edit_perm, quant_data_view_perm, quant_data_upload_perm, quant_data_edit_perm, administation_data_view_perm, administation_data_upload_perm, administation_data_edit_perm, system_edit_perm

from . import main

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        if shorts_summary_meta:
            stock_news_daily = shorts_summary_meta.get("shorts_summary", '')
            
        else:
            stock_news_daily = ''
        # 將新聞存入redis中，並設置過期時間為60秒
        redis_instance.set(redis_key, stock_news_daily, ex=60)
        
    # 若redis中有此日期的新聞，則直接取得（redis中的資料為bytes，需轉為utf-8）
    else:
        logging.info("redis_value is not None")
        stock_news_daily = redis_value.decode('utf-8')
    
    return jsonify({"date": date_str, "stock_news_daily": stock_news_daily})

@main.route('/')
@main.route("/dashboard")
@login_required
def dashboard():
    return render_template('index.html', title='Dashboard')

@main.route("/set_user_setting", methods=['POST'])
@login_required
def set_user_setting():
    if request.form:
        new_readwise_token = request.form.get("readwise_token", '')
        # 針對user的checkbox設置是否寄信
        raw_send_report_to_email = request.form.get("send_report_to_email", '')
        send_report_to_email = False
        if raw_send_report_to_email == "yes":
            send_report_to_email = True
        
        MDB_client["users"]["user_basic_info"].update_one(
            {"_id": ObjectId(current_user.get_id())},
            {"$set": {"readwise_token": new_readwise_token,
                      "send_report_to_email": send_report_to_email}},
            upsert=True
        )
        flash("User setting updated successfully!", "success")

    return redirect(url_for("main.show_user_setting"))

@main.route('/show_user_setting')
@login_required
def show_user_setting():
    user_info_dict = MDB_client["users"]["user_basic_info"].find_one({"_id" : ObjectId(current_user.get_id())})
    readwise_token = user_info_dict.get("readwise_token", '')
    send_report_to_email = user_info_dict.get("send_report_to_email", '')
    employee_id = user_info_dict.get("employee_id", '')
    
    context = {
        "readwise_token": readwise_token,
        "send_report_to_email": send_report_to_email,
        "employee_id": employee_id,
    }
    return render_template("user_setting.html", **context)

@main.route("/pool_list_review")
# @login_required
def pool_list_review():
    pool_list_df = pool_list_db.get_pool_list_data_df()
    pool_list_df = pool_list_df.loc[:, ["researcher", "holding_status", "tracking_status", "last_publication_timestamp"]]
    
    pool_list_meta_list = (
        pool_list_db.get_pool_list_data_df()
        .loc[:, ["researcher", "holding_status", "tracking_status", "last_publication_timestamp"]]
        # 將部位資訊轉換為字串，以逗號分割，便於前端顯示
        .assign(holding_status=lambda df: df["holding_status"].fillna('').apply(lambda x: ','.join(x) if x else ''))
        .astype({"last_publication_timestamp": str, "tracking_status": int})
        .replace('NaT', '')
        .fillna('')
        .reset_index()
        .rename(columns={"index": "ticker"})
        .to_dict(orient="records")
    )
        
    return render_template('pool_list_review.html', pool_list_meta_list=pool_list_meta_list)

@main.route('/ticker_internal_info/<ticker>')
def ticker_internal_info(ticker):
    updated_timestamp = ''
    publication_type_list = []
    publication_count_list = []
    publications_meta_list = []
    
    # 取得個股內部觀點(使用pool_list_db物件)
    conclustion_meta = pool_list_db.get_conclustion_meta_list(ticker=ticker)
    if conclustion_meta:
        conclustion_meta["data_timestamp"] = datetime2str(conclustion_meta["data_timestamp"])
    
    # 製作username與employee_id的對應表
    user_info_meta_list = list(MDB_client["users"]["user_basic_info"].find())
    mapping_df = pd.DataFrame(user_info_meta_list).loc[:, ["username", "employee_id"]].set_index("employee_id")
    id_mapping_dict = mapping_df.to_dict(orient='index')
    
    # 取得個股內部報告
    research_status_dict = MDB_client["pool_list"]["research_status"].find_one({"ticker": ticker})
    if research_status_dict:
        updated_timestamp = datetime2str(research_status_dict["updated_timestamp"])
        publications_meta_list = research_status_dict["publications"]
    
        for publication_meta in publications_meta_list:
            # 將data_timestamp轉換為字串
            publication_meta["data_timestamp"] = datetime2str(publication_meta["data_timestamp"])
            # 將author_id轉換為username
            publication_meta["author"] = id_mapping_dict[publication_meta["author_id"]]["username"]
                
        if publications_meta_list:
            # 提取 publication type 并统计数量
            publication_counts_series = (pd.Series(Counter(item['type'] for item in publications_meta_list))
                                        .rename(index={"Preliminary": "初步研究", "Comprehensive": "深入研究", "Initial": "初次推薦", "Supplemental": "補充研究", "Model": "財務模型"}))

            publication_type_list = publication_counts_series.index.tolist()
            publication_count_list = publication_counts_series.values.astype(int).tolist()
    
    context = {
        "ticker": ticker,
        "updated_timestamp": updated_timestamp,
        'conclustion_meta': conclustion_meta,
        'publication_type_list': publication_type_list,
        'publication_count_list': publication_count_list,
        'publications_meta_list': publications_meta_list,
    }
    return render_template('ticker_internal_info.html', **context)

@main.route('/ticker_market_info/<ticker>')
# @login_required
# @cache.cached(timeout=60)  #緩存60秒
@us_data_view_perm.require(http_exception=403)
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
@us_data_view_perm.require(http_exception=403)
def ticker_setting_info(ticker):
    # 取得個股的投資假設
    assumption_meta_list = list(MDB_client["users"]["investment_assumptions"].find({"tickers": ticker}))
    for assumption_meta in assumption_meta_list:
        # 將_id轉為str，以便前端綁定於class
        assumption_meta['_id'] = str(assumption_meta["_id"])
        assumption_meta["upload_timestamp"] = datetime2str(assumption_meta.get("upload_timestamp", ''))
        assumption_meta["updated_timestamp"] = datetime2str(assumption_meta.get("updated_timestamp", ''))
    
    # 取得用戶上傳的追蹤問題列表
    issue_meta_list = list(MDB_client["users"]["following_issues"].find({"tickers": ticker}))
    for issue_meta in issue_meta_list:
        # 將_id轉為str，以便前端綁定於class
        issue_meta['_id'] = str(issue_meta["_id"])
        issue_meta["upload_timestamp"] = datetime2str(issue_meta.get("upload_timestamp", ''))
        issue_meta["updated_timestamp"] = datetime2str(issue_meta.get("updated_timestamp", ''))
    
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

@main.route("/report_summary_page/<report_id>")
@login_required
@us_data_view_perm.require(http_exception=403)
def report_summary_page(report_id):
    stock_report_meta = MDB_client["preprocessed_content"]["stock_report"].find_one({"_id": ObjectId(report_id)})
    title = stock_report_meta["title"][:-4]
    report_date = datetime2str(stock_report_meta["data_timestamp"])
    source = stock_report_meta["source"]
    url = stock_report_meta["url"]
    summary =  stock_report_meta["summary"]
    issue_meta_list =  stock_report_meta.get("issue_summary", [])
    
    issue_summary = {} 
    for issue_meta in issue_meta_list:
        issue = issue_meta["issue"]
        issue_content = issue_meta["issue_content"]
        issue_summary[issue] = issue_content
        
    # 格式美觀：原title有許多'_'，將其拆解後重組
    title = " ".join(title.split("_"))
    source_trans_dict = {"gs": "Goldman Sachs", "jpm":"J.P. Morgan", "citi":"Citi", "barclays":"Barclays"}
    if source in source_trans_dict.keys():
        source = source_trans_dict[source]

    return render_template('report_summary_page.html', 
                           title=title, 
                           report_date=report_date,
                           source=source,
                           url=url, summary=summary,
                           issue_summary=issue_summary)

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
    
    item_meta_list = list(collection.find())
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

    context = {
        "item_meta_list": item_meta_list,
        "item_title": item_title,
    }
    
    return render_template("investment_assumption_review.html", **context)

@main.route("/investment_issue_review/<item_id>")
def investment_issue_review(item_id):
    item_meta_list = list(MDB_client["published_content"]["issue_review"].find({"issue_id": ObjectId(item_id)}))
    
    item_title = ''
    if item_meta_list:
        item_title = item_meta_list[0]["issue"]
        
    item_meta_list = sorted(item_meta_list, key=lambda x: x['upload_timestamp'], reverse=True)
    for item_meta in item_meta_list:
        item_meta["upload_timestamp"] = datetime2str(item_meta["upload_timestamp"])

    context = {
        "item_meta_list": item_meta_list,
        "item_title": item_title,
    }
    
    return render_template("investment_issue_review.html", **context)

@main.route('/upload_stock_report', methods=['POST'])
@login_required
@us_data_upload_perm.require(http_exception=403)
def upload_stock_report():
    ticker, source, file_list = request.form["ticker"], request.form["source"], request.files.getlist('files')
    file_name_list = [file.filename for file in file_list]
    # 若有檔名命名錯誤，紀錄在error_file_name_list，並跳轉至report_upload_result頁面
    error_file_name_list = [file_name for file_name in file_name_list if is_valid_report_name(file_name) == False]
    # 若有檔名命名錯誤，並顯示錯誤檔名
    if len(error_file_name_list) > 0:
        return render_template('report_upload_result.html', file_name_list=error_file_name_list, upload_success=False)
    
    GCS_folder_name = "US_stock_report"
    # 生成文件元数据
    upload_timestamp = str(int(datetime.now().timestamp()))
    blob_meta_list = []
    for file in file_list:
        blob_name = os.path.join(GCS_folder_name, ticker, file.filename)
        # 檔案名前10碼為日期（2024-01-01)，轉為unix timestamp，加int是為了去除小數點，否則在後續處理可能會報錯
        data_timestamp = int(str2datetime(file.filename[:10]).timestamp())
        blob_meta = {
            "blob_name": blob_name,
            "file_type": "file",
            "file": file,
            "metadata": {
                "data_timestamp": data_timestamp,  
                "upload_timestamp": upload_timestamp,
                "title":  file.filename[11:], # 檔案名前10碼為日期，第10碼為'_'，故從第11碼開始為檔案名
                "ticker": ticker,
                "uploader_id": current_user.get_id(),
                "source": source,
            }
        }
        blob_meta_list.append(blob_meta)
    
    # 將file meta上傳至google cloud storage
    blob_url_dict = google_cloud_storage_tools.upload_to_google_cloud_storage(
        bucket_name="investment_report", 
        blob_meta_list=blob_meta_list
    )

   # 上傳成功後，準備MongoDB元數據（因需要url，故2個for loop不能合併）
    mongo_db_data_list = []
    for file in file_list:
        blob_name = os.path.join(GCS_folder_name, ticker, file.filename)
        mongo_db_data_meta = {
            "blob_name": blob_name,
            "data_timestamp": str2datetime(file.filename[:10]), # 前10码为日期（ex: 2024-01-01）
            "upload_timestamp": unix_timestamp2datetime(upload_timestamp),
            "title": file.filename[11:],  # 去除日期后的文件名
            "ticker": ticker,
            "uploader": ObjectId(current_user.get_id()),
            "source": source,
            "url": blob_url_dict[blob_name],
            "is_processed": False # 標註為尚未進行預處理
        }
        mongo_db_data_list.append(mongo_db_data_meta)
    
    MDB_client["raw_content"]["raw_stock_report_non_auto"].insert_many(mongo_db_data_list)
    return render_template('report_upload_result.html', file_name_list=file_name_list, upload_success=True)

@main.route("investment_document_search", methods=['POST'])
@login_required
@us_data_view_perm.require(http_exception=403)
@tw_data_view_perm.require(http_exception=403)
def investment_document_search():
    document_meta_list = list()
    country = request.form["country"]
    ticker_list = [ticker.strip() for ticker in request.form["ticker"].split(",")]
    if country == "TW":
        ticker_list = [ticker+"_TT" for ticker in ticker_list if ticker != '']
    # equity_type: stock/industry; document_type: memo/report
    equity_type, document_type = request.form["document_type"].split("_")
    # 若用戶未填寫日期，表單值為空字串''
    start_date = request.form["start_date"] or None
    end_date = request.form["end_date"] or None
    # 若有日期範圍，則轉換為datetime格式
    start_date = str2datetime(start_date) if start_date else None
    # 若有結束日期，則加一天，以包含結束日
    end_date = str2datetime(end_date) + timedelta(days=1) if end_date else None
    
    if ticker_list:
        for ticker in ticker_list:
            document_meta_list.extend(search_investment_gcs_document(country, equity_type, document_type, ticker, start_date, end_date))
    
    # 若未填寫ticker，代表用戶搜尋行業文件，因此不用給定ticker
    else:
        document_meta_list.extend(search_investment_gcs_document(country=country, equity_type=equity_type, document_type=document_type, 
                                                                 start_date=start_date, end_date=end_date))
    # 根据上传时间排序（最新的在前面）
    document_meta_list = sorted(document_meta_list, key=lambda x: x["data_timestamp"], reverse=True)
    return render_template('stock_document_search.html', document_meta_list=document_meta_list)

@main.route('/quick_search_investment_document/<int:days>/<string:folder_name>')
@login_required
@us_data_view_perm.require(http_exception=403)
@tw_data_view_perm.require(http_exception=403)
def quick_search_investment_document(days, folder_name):
    document_meta_list = search_recent_investment_gcs_document(days, [folder_name])
    document_meta_list = sorted(document_meta_list, key=lambda x: x["data_timestamp"], reverse=True)
    return render_template('stock_document_search.html', document_meta_list=document_meta_list)

@main.route("edit_gcs_stock_document_metadata", methods=['POST'])
@login_required
@us_data_edit_perm.require(http_exception=403)
@tw_data_edit_perm.require(http_exception=403)
def edit_gcs_stock_document_metadata():
    edit_metadata = request.get_json()
    blob_name = edit_metadata["blob_name"]
    # 转换为 datetime 对象
    datetime_obj = datetime.strptime(edit_metadata["datetime_str"], '%Y-%m-%d %H:%M:%S')
    # 转换为 Unix timestamp
    unix_timestamp = int(datetime_obj.timestamp())
    data_source = edit_metadata["data_source"]
    
    new_metadata = {
        "data_timestamp": unix_timestamp,
        "source": data_source
    }
    try:
        google_cloud_storage_tools.set_blob_metadata(bucket_name='investment_report', blob_name=blob_name, metadata=new_metadata)
        return jsonify({'status': 'success', 'message': 'updated seccessfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@main.route("delete_gcs_document", methods=['POST'])
@login_required
@us_data_edit_perm.require(http_exception=403)
@tw_data_edit_perm.require(http_exception=403)
def delete_gcs_document():
    edit_metadata = request.get_json()
    blob_name = edit_metadata["blob_name"]
    logging.info(blob_name, "deleted")
    try:
        # google_cloud_storage_tools.set_blob_metadata(bucket_name='investment_report', blob_name=blob_name, metadata=new_metadata)
        return jsonify({'status': 'success', 'message': 'Delete seccessfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@main.route('/download_content/<path:blob_name>')
def download_GCS_file(blob_name):
    blob = google_cloud_storage_tools.get_blob(bucket_name='investment_report', blob_name=blob_name)
    # 建立一个内存中的文件對象，並下載blob内容到内存
    file_obj = io.BytesIO(blob.download_as_bytes())
    # 將文件指標移至文件開頭（否者會導致讀取不到文件）
    file_obj.seek(0)
    # 傳送下載文件给用户，并設置檔案名稱（取blob_name的最後一部分作為檔案名稱）
    return send_file(file_obj, as_attachment=True, download_name=blob_name.split("/")[-1])

@main.route('/get_content/<path:blob_name>')
def get_GCS_text_file_content(blob_name):
    blob = google_cloud_storage_tools.get_blob(bucket_name='investment_report', blob_name=blob_name)
    # 读取文件内容
    content = blob.download_as_text()
    return jsonify({"content": content})

@main.route("/note_search_page")
@login_required
def note_search_page(tag_show_days=30):
    user_id = current_user.get_id()
    user_info = MDB_client["users"]["user_basic_info"].find_one({"_id": ObjectId(user_id)}, {"readwise_token": 1, "_id": 0})
    readwise_token = user_info.get("readwise_token", '')
    if readwise_token == '':
        flash("Please set Readwise token first!", "danger")
        return redirect(url_for("main.show_user_setting"))
    # 建立ReadwiseTool實例
    # 將用戶的筆記上傳至mongodb
    readwise_client.token = readwise_token
    readwise_client.upload_articles_to_MDB(user_id=user_id)
    lastest_article_date = datetime2str(readwise_client.get_lastest_article_date(user_id=user_id))
    # 取得最近（預設為30日）的tag list，以供用戶選擇
    article_meta_list = readwise_client.get_article_meta_list(user_id=user_id, days=tag_show_days)
    recent_tag_list = readwise_client.get_recent_tag_list(article_meta_list)
    
    # 回傳時，如何辨別出哪些是topic tag，哪些是stock tag？
    # stock_tag_list = sorted([tag.upper() for tag in recent_tag_list if len(tag.split("_")) == 1])
    # topic_tag_list = sorted(['_'.join(tag.split("_")[1:]).upper() for tag in recent_tag_list if len(tag.split("_")) > 1])
    
    # 將tag list排序並轉為upper case
    recent_tag_list = sorted([tag.upper() for tag in recent_tag_list])
    
    context = {
        "lastest_article_date": lastest_article_date,
        "recent_tag_list": recent_tag_list,
    }
    return render_template("note_search_page.html", **context)

# 重新加載筆記，預設天數為30天
@main.route("/note_reload")
@login_required
def note_reload(reload_days=30):
    user_id = current_user.get_id()
    # user_info = MDB_client["users"]["user_basic_info"].find_one({"_id": ObjectId(user_id)}, {"readwise_token": 1, "_id": 0})
    readwise_client.upload_articles_to_MDB(user_id=ObjectId(user_id), days=reload_days)
    return note_search_page()

@main.route("/note_search", methods=['POST'])
def note_search():
    data = request.json
    days = data.get("days")
    tag_list = data.get("tag_list")
    article_meta_list = readwise_client.get_article_meta_list(days=days)
    selected_article_meta_list = readwise_client.search_highlights_by_tags(article_meta_list, tag_list)
    selected_article_meta_list = convert_objectid_to_str(selected_article_meta_list)
    return jsonify(selected_article_meta_list)

@main.route('/new_user_register')
@login_required
@system_edit_perm.require(http_exception=403)
def new_user_register():
    return redirect(url_for("auth.user_register"))

@main.route('/notifications/<user_id>', methods=['GET'])
def get_recent_notifications(user_id, num_limit=5):
    """取得用戶未讀取的通知"""
    collection = MDB_client["users"]["notifications"]
    undisplayed_notification_num = len(list(collection.find({"user_id": ObjectId(user_id),
                                                        "is_displayed": False})))
                                                                            
    recent_notification_meta_list = list(collection.find({"user_id": ObjectId(user_id)},
                                                        sort=[("upload_timestamp", -1)],
                                                        limit=num_limit))
    for notification_meta in recent_notification_meta_list:
        notification_meta["_id"] = str(notification_meta["_id"])
    
    return undisplayed_notification_num, recent_notification_meta_list

@main.route('/notifications/display/<user_id>', methods=['POST'])
def mark_notification_as_displayed(user_id):
    """將指定用戶的通知標示為已展示"""
    MDB_client["users"]["notifications"].update_many(
        {"user_id": ObjectId(user_id), "is_displayed": False},
        {"$set": {"is_displayed": True}}
    )
    return jsonify({"status": "success"}), 200 

@main.route('/notifications/read/<notification_id>', methods=['POST'])
def mark_notification_as_read(notification_id):
    """將指定的通知標示為已讀取"""
    result = MDB_client["users"]["notifications"].update_one(
        {"_id": ObjectId(notification_id)},
        {"$set": {"is_read": True}}
    )
    if result.matched_count > 0:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", "message": "Notification not found"}), 404

@main.before_request
def before_request():
    """在每次請求之前執行，獲取用戶的通知"""
    if '_user_id' in session:  # 假設用戶ID保存在session中
        g.undisplayed_notification_num, g.recent_notification_meta_list = get_recent_notifications(user_id=session['_user_id'])
    else:
        g.recent_notification_meta_list = []
        
@main.route('/<page>')
@login_required
def render_static_html(page):
    return render_template(f"{page}.html")

if __name__ == '__main__':
    app.run(debug=True)
    
    