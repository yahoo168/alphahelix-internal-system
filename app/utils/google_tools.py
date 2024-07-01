import sys
# 添加包路径到sys.path，用於本地調適
#sys.path.append('/Users/yahoo168/Desktop/')
from alphahelix_database_tools.external_tools import google_tools
from datetime import datetime, timedelta
import os
import logging

# 後者用於本地調適，前者用於部署至Heroku
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
google_cloud_storage_tools = google_tools.GoogleCloudStorageTools(GOOGLE_APPLICATION_CREDENTIALS)

# 將原始的GCS資料整理並篩選（過濾）出符合條件的文件，因GCS不支援依照時間搜尋，只能全部取出後再篩選
def _organize_blob_to_document_meta(blob_list, start_date, end_date, document_type):
    document_meta_list = list()
    for blob in blob_list:
        #使用try-except避免因metadata不完整而導致程式中斷，影響用戶搜索
        try:
            upload_timestamp = datetime.fromtimestamp(int(blob.metadata["upload_timestamp"]))
            # 若未載明資料時間(data_timestamp)，則以上傳時間替代
            if "data_timestamp" in blob.metadata:
                data_timestamp = datetime.fromtimestamp(int(blob.metadata["data_timestamp"]))
            else:
                data_timestamp = upload_timestamp
            
            # 检查开始日期和结束日期
            if (start_date is not None and data_timestamp < start_date) or \
            (end_date is not None and data_timestamp > end_date):
                continue
                
            document_meta_list.append({"upload_timestamp": upload_timestamp,
                                        "data_timestamp": data_timestamp,
                                        "source": blob.metadata["source"],
                                        #去除folder路徑和副檔名，用於頁面呈現（最多70個字，避免影響頁面）
                                        "file_name": blob.name.split("/")[-1].split(".")[0][:50], 
                                        "url": blob.public_url,
                                        "blob_name": blob.name,
                                        "document_type": document_type})
        except Exception as e:
            logging.error(f"Error in _organize_blob_to_document_meta: {e}")
            continue
    return document_meta_list

# 搜尋特定市場（TW/US）的股票文件（memo或report）
def search_investment_gcs_document(country, equity_type, document_type, ticker=None, start_date=None, end_date=None):
    # 如果有ticker，則搜尋特定ticker的文件，否則搜尋所有文件
    if ticker:
        folder_name = f"{country}_{equity_type}_{document_type}/{ticker}"
    else:
        folder_name = f"{country}_{equity_type}_{document_type}/"
    
    blob_list = google_cloud_storage_tools.get_blob_list_in_folder(bucket_name="investment_report", folder_name=folder_name)
    document_meta_list = _organize_blob_to_document_meta(blob_list, start_date, end_date, document_type)
    return document_meta_list

# 搜尋近期的GCS document（以data_timestamp為搜尋基礎，若data_timestamp不存在則以upload_timestamp為搜尋基礎）
def search_recent_investment_gcs_document(days=1, folder_name_list=None):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    # 搜尋所有的投資文件（待添加）
    # folder_name_list = ["TW_industry_report", "TW_stock_memo", "TW_stock_report", "US_stock_report"]    
    document_meta_list = list()
    for folder_name in folder_name_list:
        document_type = folder_name.split("_")[-1]
        _part_blob_list = google_cloud_storage_tools.get_blob_list_in_folder(bucket_name="investment_report", folder_name=folder_name)
        _part_document_meta_list = _organize_blob_to_document_meta(_part_blob_list, start_date, end_date, document_type)
        document_meta_list.extend(_part_document_meta_list)

    return document_meta_list