from flask import request, jsonify, render_template, send_file
from flask import current_app as app
from flask_login import login_required, current_user

import io, logging

from datetime import datetime, timedelta
from bson import ObjectId
from app.utils.google_tools import google_cloud_storage_tools, search_investment_gcs_document, search_recent_investment_gcs_document
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import TODAY_DATE_STR, datetime2str, str2datetime

from app.utils.alphahelix_database_tools import pool_list_db

# 引入權限設定
# from app import us_data_view_perm, us_data_edit_perm, tw_data_view_perm, tw_data_edit_perm

from . import main

@main.route("investment_document_search", methods=['POST'])
@login_required
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
def quick_search_investment_document(days, folder_name):
    document_meta_list = search_recent_investment_gcs_document(days, [folder_name])
    document_meta_list = sorted(document_meta_list, key=lambda x: x["data_timestamp"], reverse=True)
    return render_template('stock_document_search.html', document_meta_list=document_meta_list)

@main.route("edit_gcs_stock_document_metadata", methods=['POST'])
@login_required
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
def get_GCS_text_file_content(blob_name, encoding='utf-8'):
    blob = google_cloud_storage_tools.get_blob(bucket_name='investment_report', blob_name=blob_name)
    # 读取文件内容
    content = blob.download_as_text(encoding=encoding)
    return jsonify({"content": content})