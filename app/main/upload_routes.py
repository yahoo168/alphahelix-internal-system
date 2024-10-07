from flask import request, render_template, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

import os
from datetime import datetime, timedelta, timezone
import pytz
from bson import ObjectId
from collections import defaultdict
import tempfile
import pandas as pd

from app.utils.google_tools import google_cloud_storage_tools
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import datetime2str, str2datetime, unix_timestamp2datetime, check_report_name_is_valid, local_timezone

# 引入權限設定
#from app import us_internal_stock_report_upload_perm, us_market_stock_report_upload_perm, system_edit_perm

from app.utils.alphahelix_database_tools import pool_list_db
from alphahelix_database_tools.utils.ticker_trans_mapping import trans_BBG_event_type, trans_BBG_main_ticker #type: ignore

from . import main

def _upload_files_to_gcs_and_mdb(gcs_bucket_name, blob_meta_list, mongoDB_collection, mongoDB_meta_list):
    # 將file meta上傳至google cloud storage，並取得url（儲存於MongoDB）
    blob_url_dict = google_cloud_storage_tools.upload_to_google_cloud_storage(
        bucket_name=gcs_bucket_name, 
        blob_meta_list=blob_meta_list
    )
    # 上傳成功後，添加blob url進MongoDB元數據
    for mongoDB_meta in mongoDB_meta_list:
        mongoDB_meta["url"] = blob_url_dict[mongoDB_meta["blob_name"]]
    
    mongoDB_collection.insert_many(mongoDB_meta_list)

def _generate_blob_and_mongo_metadata(file_list, ticker, gcs_folder_name, extra_meta=None):
    blob_meta_list = []
    mongoDB_meta_list = []
    upload_timestamp = int(datetime.now(timezone.utc).timestamp())
    
    for file in file_list:
        blob_name = os.path.join(gcs_folder_name, ticker, file.filename)
        data_timestamp = int(str2datetime(file.filename[:10]).timestamp())
        title = file.filename[11:]
        current_user_id_str = current_user.get_id()
        
        blob_meta = {
            "blob_name": blob_name,
            "file_type": "file",
            "file": file,
            "metadata": {
                "data_timestamp": data_timestamp,  
                "upload_timestamp": upload_timestamp,
                "title":  title,
                "ticker": ticker,
                "uploader_id": current_user_id_str,
            }
        }
        
        if extra_meta:
            blob_meta["metadata"].update(extra_meta)
        
        blob_meta_list.append(blob_meta)
        
        mongo_db_data_meta = {
            "blob_name": blob_name,
            "data_timestamp": str2datetime(file.filename[:10]),
            "upload_timestamp": unix_timestamp2datetime(upload_timestamp),
            "title": title,  
            "ticker": ticker,
            "uploader_id": ObjectId(current_user_id_str),
            "is_processed": False
        }
        
        if extra_meta:
            mongo_db_data_meta.update(extra_meta)
        
        mongoDB_meta_list.append(mongo_db_data_meta)
    
    return blob_meta_list, mongoDB_meta_list

# 待補充：GCS bucket name
@main.route('/upload_internal_stock_report', methods=['POST'])
@login_required
#@us_internal_stock_report_upload_perm.require(http_exception=403)
def upload_internal_stock_report():
    ticker, report_type, file_list = request.form["ticker"], request.form["report_type"], request.files.getlist('files')
    file_name_list = [file.filename for file in file_list]
    error_file_name_list = check_report_name_is_valid(file_name_list)
    
    if len(error_file_name_list) > 0:
        return jsonify({
            'upload_success': False,
            'file_name_list': error_file_name_list
        })
    
    try:
        # GSC file path
        gcs_bucket_name, gcs_folder_name = "internal_investment_report", "US_stock_report"
        extra_meta = {
            "report_type": report_type
        }
        
        blob_meta_list, mongoDB_meta_list = _generate_blob_and_mongo_metadata(file_list, ticker, gcs_folder_name, extra_meta=extra_meta)
        
        mongoDB_collection = MDB_client["research_admin"]["internal_investment_report"]
        _upload_files_to_gcs_and_mdb(gcs_bucket_name, blob_meta_list, mongoDB_collection, mongoDB_meta_list)
        
        return jsonify({
                'upload_success': True,
                'file_name_list': [f.filename for f in file_list]
            })
        
    except Exception as e:
        print(f"Error in upload_internal_stock_report: {e}")
        return jsonify({
            'upload_success': False,
            'file_name_list': []
        })
        
@main.route('/upload_market_stock_report', methods=['POST'])
#@us_market_stock_report_upload_perm.require(http_exception=403)
@login_required
def upload_market_stock_report():
    ticker, source, file_list = request.form["ticker"], request.form["source"], request.files.getlist('files')
    # 檢查檔名是否符合規定
    file_name_list = [file.filename for file in file_list]
    # 若有檔名命名錯誤，紀錄在error_file_name_list，並跳轉回頁面顯示
    error_file_name_list = check_report_name_is_valid(file_name_list)
    
    if len(error_file_name_list) > 0:
        return jsonify({
            'upload_success': False,
            'file_name_list': error_file_name_list
        })
            
    # GSC file path
    gcs_bucket_name, gcs_folder_name = "investment_report", "US_stock_report"
    
    extra_meta = {
        "source": source
    }
    
    blob_meta_list, mongoDB_meta_list = _generate_blob_and_mongo_metadata(file_list, ticker, gcs_folder_name, extra_meta=extra_meta)
    mongoDB_collection = MDB_client["raw_content"]["raw_stock_report_non_auto"] 
    _upload_files_to_gcs_and_mdb(gcs_bucket_name, blob_meta_list, mongoDB_collection, mongoDB_meta_list)
    
    return jsonify({
            'upload_success': True,
            'file_name_list': [f.filename for f in file_list]
        })
    
    
@main.route('/create_ticker_info_page')
@login_required
def create_ticker_info_page():
    user_meta_list = list(MDB_client["users"]["user_basic_info"].find({"is_active": True, 
                                                                       "roles": {"$in": ["investment_manager", "investment_researcher", "investment_intern"]}},
                                                                      # Projection
                                                                      {"_id": 1, "username": 1, "roles": 1}
                                                                ))
    
    for user_meta in user_meta_list:
        # Capitalize the first letter of each word in a string?
        user_meta["username"] = ' '.join(user_meta["username"].split("_")).title()
        
    return render_template("ticker_info_create.html", user_meta_list=user_meta_list)
    

@main.route('/adjust_ticker_info_page')
@login_required
def adjust_ticker_info_page(http_exception=403):
    return render_template("ticker_info_adjust.html")

@main.route('/create_ticker_info', methods=['POST'])
@login_required
def create_ticker_info(http_exception=403):
    creator_id = current_user.get_id()
    ticker = request.form["ticker"]
    
    # 檢查研究資料庫是否已存在該ticker
    ticker_info_exist = pool_list_db.check_ticker_info_exist(ticker)
    
    if ticker_info_exist:
        flash("Ticker info already exists in database. Please Check", "danger")
        return redirect(url_for('main.create_ticker_info_page'))

    else:
        profit_rating = request.form["profit_rating"]
        risk_rating = request.form["risk_rating"]    
        researcher_id = request.form["researcher_id"]
        investment_thesis = request.form.get("investment_thesis", None)
        
        result = pool_list_db.create_ticker_info(creator_id, ticker, investment_thesis, profit_rating, risk_rating, researcher_id)
        
        if result:
            flash("Ticker info created successfully", "success")
        else:
            flash("Ticker info creation failed", "danger")
        
        return redirect(url_for('main.create_ticker_info_page'))

@main.route('/market_stock_report_upload_record', methods=['GET', 'POST'])
@login_required
def market_stock_report_upload_record():
    if request.method == 'POST':
        monitor_period_days = int(request.form["days_before"])
    else:
        monitor_period_days = 30
        
    record_meta_list = pool_list_db.get_market_report_upload_record(monitor_period_days)
    id_to_username_mapping_dict = pool_list_db.get_id_to_username_mapping_dict()
    # Sort the list by ticker(Alphabetical order)
    record_meta_list.sort(key=lambda x: x["ticker"])
    for record_meta in record_meta_list:
        record_meta["uploader"] = id_to_username_mapping_dict.get(record_meta["uploader_id"], "Unknown").replace("_", " ").title()
        # 轉換時區（UTC to local）
        record_meta["upload_timestamp"] = record_meta["upload_timestamp"].replace(tzinfo=timezone.utc).astimezone(local_timezone)
        record_meta["data_timestamp"] = datetime2str(record_meta["data_timestamp"])
        record_meta["source"] = record_meta["source"].replace("_", " ").title()
        
    return render_template('market_stock_report_upload_record.html', 
                           record_meta_list=record_meta_list, 
                           monitor_period_days=monitor_period_days)

@main.route('/pretrade_check', methods=['POST'])
@login_required
def pretrade_check():
    # 解析表單中的ticker list（str），並去除空格與重複的ticker
    ticker_list = list(set([ticker.strip() for ticker in request.form["ticker_list"].split(",")]))
    
    maximum_days = 100  # Relaxed constraint of 100 days as per IPS (at least one report per quarter)
    pretrade_check_meta_list = []
    
    for ticker in ticker_list:
        # Fetch ticker info
        ticker_info_meta_list = pool_list_db.get_latest_ticker_info_meta_list(ticker_list=[ticker])
        # 輸入的ticker有可能不存在於資料庫，直接取index 0會出錯，# 若ticker不存在於資料庫，則in_pool_list為False
        in_pool_list = ticker_info_meta_list[0]["poolList_status"]["in_poolList"] if ticker_info_meta_list else False
        
        # 依據ticker取得最新的內部報告時間戳記
        report_meta = MDB_client["research_admin"]["internal_investment_report"].find_one(
            {"ticker": ticker},
            projection={"_id": 0, "data_timestamp": 1},
            sort=[("data_timestamp", -1)]
        )
        
        # 若有報告，則取得最新報告的時間戳記
        if report_meta:
            latest_report_timestamp = report_meta.get("data_timestamp")
            days_since_latest_report_date = (datetime.now() - latest_report_timestamp).days
            is_updated = days_since_latest_report_date <= maximum_days
            latest_report_date = datetime2str(latest_report_timestamp)
        else:
            latest_report_date = None
            days_since_latest_report_date = ''
            is_updated = False
        
        # Determine if the trade is executable
        is_executable = in_pool_list and is_updated
        
        # Append pre-trade check metadata
        pretrade_check_meta_list.append({
            "ticker": ticker,
            "in_poolList": in_pool_list,
            "is_updated": is_updated,
            "latest_report_date": latest_report_date,
            "days_since_latest_report_date": str(days_since_latest_report_date) + " Days" if days_since_latest_report_date else '',
            "is_executable": is_executable,
        })

        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Sort the list by ticker(Alphabetical order)
    pretrade_check_meta_list.sort(key=lambda x: x["ticker"])
    return render_template('pretrade_check_page.html', current_timestamp=current_timestamp, pretrade_check_meta_list=pretrade_check_meta_list)

@main.route('/upload_ticker_event', methods=['POST'])
@login_required
def upload_ticker_event():
    ticker, event_type, event_title, event_date = request.form["ticker"], request.form["event_type"], request.form["event_title"], request.form["event_date"]
    
    is_ticker_info_exist = pool_list_db.check_ticker_info_exist(ticker)
    if is_ticker_info_exist is False:
        flash("Event upload failed !", "danger")
        return redirect(url_for('main.render_static_html', page='ticker_event_upload'))
    
    event_timestamp = str2datetime(event_date)
    
    meta = {
        "ticker": ticker,
        "event_type": event_type,
        "event_title": event_title,
        # 以輸入的日期為準，不進行時區轉換
        "event_timestamp": event_timestamp,
        "upload_timestamp": datetime.now(timezone.utc),
        "uploader_id": ObjectId(current_user.get_id()),
        # 是否soft deleted本事件（可能是輸入錯誤）
        "is_deleted": False,
    }
    
    result = MDB_client["research_admin"]["ticker_event"].insert_one(meta)
    
    if result:
        flash("Event uploaded successfully !", "success")
    else:
        flash("Event upload failed !", "danger")
    
    return redirect(url_for('main.render_static_html', page='ticker_event_upload'))


@main.route('/upload_ticker_event_by_BBG', methods=['POST'])
@login_required
def upload_ticker_event_by_BBG():
    # 確保文件已上傳
    if 'file' not in request.files:
        flash("No file", "danger")
        return redirect(url_for('main.render_static_html', page='ticker_event_upload'))
    
    file = request.files['file']

    # 檢查文件名稱是否正確
    if file.filename != 'event_data.xlsx':
        flash("Filename is not correct", "danger")
        return redirect(url_for('main.render_static_html', page='ticker_event_upload'))

    if file:
        # 使用 TemporaryDirectory 來保存臨時文件
        with tempfile.TemporaryDirectory() as temp_folder_path:
            file_path = os.path.join(temp_folder_path, file.filename)
            file.save(file_path)
            # 讀取 Excel 文件
            event_df = pd.read_excel(file_path)

            # 選擇需要的列並重命名
            event_df = event_df.loc[:, ["Ticker", "Date", "Event Type", "Description"]]
            event_df.rename(columns={
                "Ticker": "ticker", 
                "Date": "event_timestamp", 
                "Event Type": "event_type", 
                "Description": "event_title"
            }, inplace=True)

            # 應用自定義轉換函數
            event_df["event_type"] = event_df["event_type"].apply(trans_BBG_event_type)
            event_df["ticker"] = event_df["ticker"].apply(trans_BBG_main_ticker)

            # 將資料添加上傳相關資訊，並傳送至MongoDB儲存
            event_meta_list = event_df.to_dict(orient='records')
            current_timestamp = datetime.now(timezone.utc)
            uploader_id = ObjectId(current_user.get_id())
            
            for event_meta in event_meta_list:
                event_meta.update({
                    "upload_timestamp": current_timestamp,
                    "uploader_id": uploader_id,
                    # 是否soft deleted本事件（可能是輸入錯誤）
                    "is_deleted": False,
                })
                
            MDB_client["research_admin"]["ticker_event"].insert_many(event_meta_list)
            flash("File uploaded and processed successfully!", "success")

    return redirect(url_for('main.render_static_html', page='ticker_event_upload'))