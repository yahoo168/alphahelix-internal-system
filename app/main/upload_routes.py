from flask import request, render_template, jsonify
from flask_login import login_required, current_user
import os

from datetime import datetime
from bson import ObjectId

from app.utils.google_tools import google_cloud_storage_tools
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import str2datetime, unix_timestamp2datetime, is_valid_report_name

# 引入權限設定
from app import us_data_upload_perm

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

@main.route('/upload_us_stock_report', methods=['POST'])
@login_required
@us_data_upload_perm.require(http_exception=403)
def upload_us_stock_report():
    ticker, source, file_list = request.form["ticker"], request.form["source"], request.files.getlist('files')
    # 檢查檔名是否符合規定
    file_name_list = [file.filename for file in file_list]
    # 若有檔名命名錯誤，紀錄在error_file_name_list，並跳轉回頁面顯示
    error_file_name_list = [file_name for file_name in file_name_list if is_valid_report_name(file_name) == False]
    # 若有檔名命名錯誤，並顯示錯誤檔名
    if len(error_file_name_list) > 0:
        # 上傳失敗，返回錯誤檔名
        return jsonify({
            'upload_success': False,
            'file_name_list': error_file_name_list
        })
            
    GCS_folder_name = "US_stock_report"
    # 生成文件元数据
    upload_timestamp = str(int(datetime.now().timestamp()))
    
    blob_meta_list = []
    mongoDB_meta_list = []
    
    # 生成GCS文件元数据（blob_meta_list）和MongoDB元數據（mongoDB_meta_list）
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
        
        blob_name = os.path.join(GCS_folder_name, ticker, file.filename)
        mongo_db_data_meta = {
            "blob_name": blob_name,
            "data_timestamp": str2datetime(file.filename[:10]), # 前10码为日期（ex: 2024-01-01）
            "upload_timestamp": unix_timestamp2datetime(upload_timestamp),
            "title": file.filename[11:],  # 去除日期后的文件名
            "ticker": ticker,
            "uploade_id": ObjectId(current_user.get_id()),
            "source": source,
            "is_processed": False # 標註為尚未進行預處理
        }
       
        mongoDB_meta_list.append(mongo_db_data_meta)
    
    gcs_bucket_name = "investment_report"
    mongoDB_collection = MDB_client["raw_content"]["raw_stock_report_non_auto"] 
    _upload_files_to_gcs_and_mdb(gcs_bucket_name, blob_meta_list, mongoDB_collection, mongoDB_meta_list)
    
    return jsonify({
            'upload_success': True,
            'file_name_list': [f.filename for f in file_list]
        })