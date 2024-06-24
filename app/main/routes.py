from flask import request, jsonify, render_template, redirect, url_for, flash, send_file
from flask import current_app as app
from flask_login import login_required, current_user
from flask_principal import PermissionDenied

import os, io
from datetime import datetime
from bson import ObjectId
from app.utils import *
from app.utils.mongodb_client import *
from app.utils.utils import *

from . import main

# 後者用於本地調適，前者用於部署至Heroku
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/Users/yahoo168/Desktop/GOOGLE_APPLICATION_CREDENTIALS.json") 
google_cloud_storage_tools = google_tools.GoogleCloudStorageTools(GOOGLE_APPLICATION_CREDENTIALS)

def _get_permissions():
    with app.app_context():
        return {
            # 'admin_permission': app.config['ADMIN_PERMISSION'],
            # 'sales_permission': app.config['DIRECTOR_PERMISSION'],
            # 'fundamental_permission': app.config['FUNDAMENTAL_PERMISSION'],
            # 'quant_permission': app.config['QUANT_PERMISSION'],
            # 'trial_account_permission': app.config['TRIAL_ACCOUNT_PERMISSION'],
        }

permissions = None

# 通过一个函数来初始化权限，以确保在应用上下文内调用
def initialize_permissions():
    global permissions
    permissions = _get_permissions()

# 使用 before_app_request 在应用第一次请求之前初始化权限。
@main.before_app_request
def before_request():
    if permissions is None: 
        initialize_permissions()
        print("Permissions initialized:", permissions)

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
    user_info = MDB_client["users"]["user_basic_info"].find_one({"_id" : ObjectId(current_user.get_id())})
    readwise_token = user_info.get("readwise_token", '')
    
    send_report_to_email = user_info["send_report_to_email"]
    context = {
        "readwise_token": readwise_token,
        "send_report_to_email": send_report_to_email
    }
    return render_template("user_setting.html", **context)

@main.route("/ticker_select")
@login_required
def ticker_select():
    stock_ticker_list = ["AAPL", "GOOG", "MSFT", "OXY", "LAZR", "NVTS", "QCOM", "TSLA", "NET", "ON", "OXY", "TSM"]
    bond_ticker_list = ['OXY', 'RITM', 'CXW', 'F', 'MO', 'BA']
    ticker_list = stock_ticker_list + bond_ticker_list
    ticker_list.sort()
    ticker_list = [ticker for ticker in ticker_list if ticker not in ["TLT", "LQD"]]
    return render_template('ticker_select.html', ticker_list=ticker_list)

@main.route('/company/<ticker>')
@login_required
def company_page(ticker):
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
    stock_report_review_meta = MDB_client["published_content"]["stock_report_review"].find_one({"ticker": ticker}, sort=[("date", -1)])
    if stock_report_review_meta:
        stock_report_review_date = datetime2str(stock_report_review_meta["date"])
        stock_report_review = stock_report_review_meta.get("stock_report_review", {})
        bullish_argument_list = stock_report_review.get("bullish_outlook", [])
        bearish_argument_list = stock_report_review.get("bearish_outlook", [])
        bullish_outlook_diff = stock_report_review.get("bullish_outlook_diff", '')
        bearish_outlook_diff = stock_report_review.get("bearish_outlook_diff", '')

    # 取得近期新聞摘要(stock_info_daily)
    shorts_summary_meta = MDB_client["preprocessed_content"]["shorts_summary"].find_one({"ticker": ticker}, sort=[("date", -1)])
    if shorts_summary_meta:
        stock_info_date = datetime2str(shorts_summary_meta["date"])
        stock_info_daily = shorts_summary_meta.get("shorts_summary", '')

    # 取得近期報告列表（近10篇）
    stock_report_meta_list = list(MDB_client["preprocessed_content"]["stock_report"].find({"ticker": ticker}, sort=[("date", -1)], limit=10))
    for stock_report_meta in stock_report_meta_list:
        stock_report_meta["title"] = stock_report_meta["title"].replace("_", " ")[:-4][:80]
        stock_report_meta["date"] = datetime2str(stock_report_meta["date"])
        source_trans_dict = {"gs": "Goldman Sachs", "jpm": "J.P. Morgan", "citi": "Citi", "barclays": "Barclays"}
        stock_report_meta["source"] = source_trans_dict[stock_report_meta["source"]]
        stock_report_meta["_id"] = str(stock_report_meta["_id"])

    # 取得用戶上傳的追蹤問題列表（近10個）
    issue_meta_list = list(MDB_client["users"]["following_issues"].find({"tickers": ticker}, limit=10))
    for issue_meta in issue_meta_list:
        issue_meta["upload_timestamp"] = datetime2str(issue_meta["upload_timestamp"])
        user_info_meta = MDB_client["users"]["user_basic_info"].find_one({"_id": issue_meta["uploader"]}, {"username": 1})
        issue_meta["username"] = user_info_meta.get("username", "Unknown")
        issue_review_meta = MDB_client["published_content"]["following_issue_review"].find_one({"issue_id": issue_meta["_id"]}, 
                                                                                               sort=[("upload_timestamp", -1)])
        issue_meta["issue_review_date"] = ''
        issue_meta["issue_review"] = ''
        issue_meta["issue_review_diff"] = ''
        if issue_review_meta:
            issue_meta["issue_review_date"] = datetime2str(issue_review_meta["upload_timestamp"])
            issue_meta["issue_review"] = issue_review_meta.get("issue_review", '')
            issue_meta["issue_review_diff"] = issue_review_meta.get("issue_review_diff", '')

    # 在 render_template 中使用 **context 將字典展開為關鍵字參數
    
    context = {
        'company_ticker': ticker,
        'stock_report_review_date': stock_report_review_date,
        'bullish_argument_list': bullish_argument_list,
        'bearish_argument_list': bearish_argument_list,
        'bullish_outlook_diff': bullish_outlook_diff,
        'bearish_outlook_diff': bearish_outlook_diff,
        'stock_info_date': stock_info_date,
        'stock_info_daily': stock_info_daily,
        'stock_report_meta_list': stock_report_meta_list,
        'issue_meta_list': issue_meta_list,
    }
    return render_template('company.html', **context)

@main.route("/report_summary_page/<report_id>")
@login_required
def report_summary_page(report_id):
    stock_report_meta = MDB_client["preprocessed_content"]["stock_report"].find_one({"_id": ObjectId(report_id)})
    title = stock_report_meta["title"][:-4]
    date = datetime2str(stock_report_meta["date"])
    source = stock_report_meta["source"]
    url = stock_report_meta["url"]
    summary =  stock_report_meta["summary"]
    
    # 格式美觀：
    # 原title有許多'_'，將其拆解後重組
    title = " ".join(title.split("_"))
    # 原title有許多'_'，將其拆解後重組
    source_trans_dict = {"gs": "Goldman Sachs", "jpm":"J.P. Morgan", "citi":"Citi", "barclays":"Barclays"}
    if source in source_trans_dict.keys():
        source = source_trans_dict[source]

    return render_template('report_summary_page.html', title=title, date=date, source=source, url=url,summary=summary)

@main.route('/upload_stock_report', methods=['POST'])
# @login_required
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
        blob_meta = {
            "blob_name": blob_name,
            "file": file,
            "file_type": "file",
            "metadata": {
                "date": file.filename[:10],  # 前10码为日期（ex: 2024-01-01
                "upload_timestamp": upload_timestamp,
                "title":  file.filename[11:],
                "ticker": ticker,
                "uploader": current_user.get_id(),
                "source": source,
            }
        }
        blob_meta_list.append(blob_meta)
    # 將file meta上傳至google cloud storage
    blob_url_dict = upload_to_google_cloud_storage(bucket_name="investment_report", blob_meta_list=blob_meta_list) # type: ignore
    
   # 准备 MongoDB 数据
    mongo_db_data_list = []
    for file in file_list:
        blob_name = os.path.join(GCS_folder_name, ticker, file.filename)
        mongo_db_data_meta = {
            "blob_name": blob_name,
            "date": str2datetime(file.filename[:10]), # 前10码为日期（ex: 2024-01-01）
            "upload_timestamp": unix_timestamp2datetime(upload_timestamp),
            "title": file.filename[11:],  # 去除日期后的文件名
            "ticker": ticker,
            "uploader": ObjectId(current_user.get_id()),
            "source": source,
            "url": blob_url_dict[blob_name]
        }
        mongo_db_data_list.append(mongo_db_data_meta)
    
    MDB_client["raw_content"]["raw_stock_report_non_auto"].insert_many(mongo_db_data_list)
    return render_template('report_upload_result.html', file_name_list=file_name_list, upload_success=True)

@main.route("stock_document_search", methods=['POST'])
# @login_required
def stock_document_search():
    document_meta_list = list()
    print(request.form)
    country = request.form["country"]
    ticker_list = [ticker.strip() for ticker in request.form["ticker"].split(",")]
    document_type = request.form["document_type"]
    
    for ticker in ticker_list:
        if country == "TW":
            ticker += "_TT"
        document_meta_list.extend(_search_TW_stock_document(ticker, country, document_type))

    # 根据上传时间排序（最新的在前面）
    document_meta_list = sorted(document_meta_list, key=lambda x: x["upload_timestamp"], reverse=True)
    return render_template('stock_document_search.html', document_meta_list=document_meta_list)

def _search_TW_stock_document(ticker, country="US", document_type="report", start_date=None, end_date=None):
    folder_name = f"{country}_stock_{document_type}/{ticker}"
    blob_list = google_cloud_storage_tools.get_blob_list_in_folder(bucket_name="investment_report", folder_name=folder_name)
    document_meta_list = list()
    for blob in blob_list:
        upload_timestamp = datetime.fromtimestamp(int(blob.metadata["upload_timestamp"]))
        # 检查开始日期和结束日期
        if (start_date is not None and upload_timestamp < start_date) or \
           (end_date is not None and upload_timestamp > end_date):
            continue
            
        document_meta_list.append({"upload_timestamp": upload_timestamp, 
                                    "source": blob.metadata["source"],
                                    #去除folder路徑和副檔名，用於頁面呈現（最多70個字，避免影響頁面）
                                    "file_name": blob.name.split("/")[-1].split(".")[0][:70], 
                                    "url": blob.public_url,
                                    "blob_name": blob.name,
                                    "document_type": document_type})
    return document_meta_list

@main.route('/download_content/<path:blob_name>')
def download_GCS_file(blob_name):
    # 下载 blob 内容到内存
    blob = google_cloud_storage_tools.get_blob(bucket_name='investment_report', blob_name=blob_name)
    blob_data = blob.download_as_bytes()
    # 创建一个内存中的文件对象
    file_obj = io.BytesIO(blob_data)
    file_obj.seek(0)
    # 返回文件给用户，并设置默认下载名
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
    readwise_tool = readwise_tools.ReadwiseTool(MDB_client, token=readwise_token)
    # 將用戶的筆記上傳至mongodb
    readwise_tool.upload_articles_to_MDB(user_id=user_id)
    lastest_article_date = datetime2str(readwise_tool.get_lastest_article_date(user_id=user_id))
    # 取得最近（預設為30日）的tag list，以供用戶選擇
    article_meta_list = readwise_tool.get_article_meta_list(user_id=user_id, days=tag_show_days)
    recent_tag_list = readwise_tool.get_recent_tag_list(article_meta_list)
    
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
    user_info = MDB_client["users"]["user_basic_info"].find_one({"_id": ObjectId(user_id)}, {"readwise_token": 1, "_id": 0})
    readwise_token = user_info.get("readwise_token", '')
    readwise_tool = readwise_tools.ReadwiseTool(MDB_client, token=readwise_token)
    readwise_tool.upload_articles_to_MDB(user_id=ObjectId(user_id), days=reload_days)
    return note_search_page()

@main.route("/note_search", methods=['POST'])
def note_search():
    data = request.json
    days = data.get("days")
    tag_list = data.get("tag_list")
    readwise_tool = readwise_tools.ReadwiseTool(MDB_client)
    article_meta_list = readwise_tool.get_article_meta_list(days=days)
    selected_article_meta_list = readwise_tool.search_highlights_by_tags(article_meta_list, tag_list)
    selected_article_meta_list = convert_objectid_to_str(selected_article_meta_list)
    return jsonify(selected_article_meta_list)

@main.route("/summarize_articles", methods=['GET'])
@login_required
def summarize_articles():
    return render_template("summary_display.html")

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
    }
    MDB_client["users"]["following_issues"].insert_one(issue_meta)
    flash("Issue uploaded successfully!", "success")
    return render_template("issue_register.html")

@main.route('/<page>')
@login_required
def render_static_html(page):
    return render_template(f"{page}.html")

