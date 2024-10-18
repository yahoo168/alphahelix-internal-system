from flask import request, jsonify, render_template, send_file, url_for, flash
from flask import current_app as app
from flask_login import login_required, current_user

import io, logging

from datetime import datetime, timedelta
from bson import ObjectId
from app.utils.google_tools import google_cloud_storage_tools, search_investment_gcs_document, search_recent_investment_gcs_document
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import *

from app.utils.alphahelix_database_tools import pool_list_db

# 引入權限設定
# from app import us_data_view_perm, us_data_edit_perm, tw_data_view_perm, tw_data_edit_perm

from . import main

# @main.route('/quick_search_investment_document/<int:days>/<string:folder_name>')
# @login_required
# def quick_search_investment_document(days, folder_name):
#     document_meta_list = search_recent_investment_gcs_document(days, [folder_name])
#     document_meta_list = sorted(document_meta_list, key=lambda x: x["data_timestamp"], reverse=True)
#     return render_template('stock_document_search.html', document_meta_list=document_meta_list)

# @main.route("edit_gcs_stock_document_metadata", methods=['POST'])
# @login_required
# def edit_gcs_stock_document_metadata():
#     edit_metadata = request.get_json()
#     blob_name = edit_metadata["blob_name"]
#     # 转换为 datetime 对象
#     datetime_obj = datetime.strptime(edit_metadata["datetime_str"], '%Y-%m-%d %H:%M:%S')
#     # 转换为 Unix timestamp
#     unix_timestamp = int(datetime_obj.timestamp())
#     data_source = edit_metadata["data_source"]
    
#     new_metadata = {
#         "data_timestamp": unix_timestamp,
#         "source": data_source
#     }
#     try:
#         google_cloud_storage_tools.set_blob_metadata(bucket_name='investment_report', blob_name=blob_name, metadata=new_metadata)
#         return jsonify({'status': 'success', 'message': 'updated seccessfully'})
#     except Exception as e:
#         return jsonify({'status': 'error', 'message': str(e)})

# @main.route('/download_content/<path:blob_name>')
# def download_GCS_file(blob_name):
#     blob = google_cloud_storage_tools.get_blob(bucket_name='investment_report', blob_name=blob_name)
#     # 建立一个内存中的文件對象，並下載blob内容到内存
#     file_obj = io.BytesIO(blob.download_as_bytes())
#     # 將文件指標移至文件開頭（否者會導致讀取不到文件）
#     file_obj.seek(0)
#     # 傳送下載文件给用户，并設置檔案名稱（取blob_name的最後一部分作為檔案名稱）
#     return send_file(file_obj, as_attachment=True, download_name=blob_name.split("/")[-1])

# @main.route('/get_content/<path:blob_name>')
# def get_GCS_text_file_content(blob_name, encoding='utf-8'):
#     blob = google_cloud_storage_tools.get_blob(bucket_name='investment_report', blob_name=blob_name)
#     # 读取文件内容
#     content = blob.download_as_text(encoding=encoding)
#     return jsonify({"content": content})