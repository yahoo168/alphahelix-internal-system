from flask_login import current_user
from datetime import datetime, timezone
from bson import ObjectId
import os, pytz

def check_document_is_viewed(doc_meta, user_id):
    is_viewed = any(view_record["user_id"] == ObjectId(user_id) for view_record in doc_meta.get("view_by", []))
    return is_viewed

def beautify_document_for_display(doc_meta):
    # 新版的title已經不包含副檔名，故先註解
    # 去除文件的副檔名，如'.pdf'，並進行格式美化：原title有許多'_'，將其拆解後重組
    # doc_meta["title"] = os.path.splitext(doc_meta["title"])[0]
    doc_meta["title"] = doc_meta["title"].replace('_', ' ').replace('-', ' ').title()
    doc_meta["data_date_str"] = datetime2str(doc_meta["data_timestamp"])
    doc_meta["upload_date_str"] = datetime2str(doc_meta["upload_info"]["upload_timestamp"])
    # 券商名稱格式美化
    doc_meta["beautified_source"] = beautify_broker_name(doc_meta.get("source", ''))
    # 檢查該文件是否已被當前使用者瀏覽過
    doc_meta["is_viewed"] = check_document_is_viewed(doc_meta, current_user.get_id())
    return doc_meta

def beautify_broker_name(name):
    trans_dict = {"gs": "Goldman Sachs", 
                    "jpm": "J.P. Morgan", 
                    "citi": "Citi", 
                    "barclays": "Barclays",
                    "seeking_alpha": "Seeking Alpha",
                    "nomura": "Nomura",
                    "ms": "Morgan Stanley",
                    "db": "Deutsche Bank",
                    "boa": "Bank of America",
                    "ubs": "UBS",
                    "daiwa": "Daiwa",
                    "macquarie": "Macquarie",
                    "clsa": "CLSA",
                    "hsbc": "HSBC",
                    
                    "yuanta": "元大投顧",
                    "kgi": "凱基投顧",
                    "fubon": "富邦投顧",
                    "sinopac": "永豐投顧",
                    "cathay": "國泰證券",
                    "ctbc": "中信投顧",
                    "fuguo": "富果研究",
                    "capital": "群益投顧",
                    "kanghe": "康和證券",
                    "president": "統一證券",
                    "esun": "玉山投顧",
                    "yuanfu": "元富投顧",
                    "haitong": "海通國際",
                    }
    
    return trans_dict.get(name, name)

def beautify_report_title(name):
    return name.split('.')[0].replace("_", " ").title()

def _is_valid_date(date_string):
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def _is_pdf_file(file_name):
    return file_name.endswith(".pdf")

def _is_excel_file(file_name):
    return file_name.endswith(".xlsx")

# 日期格式（2024-01-01_....)，若有檔名命名錯誤，紀錄在error_file_name_list回傳
def check_report_name_is_valid(file_name_list):
    error_file_name_list = list()
    for file_name in file_name_list:
        if _is_valid_date(file_name[:10]) and (_is_pdf_file(file_name) or _is_excel_file(file_name)):
            continue
        else:
            error_file_name_list.append(file_name)
    return error_file_name_list

# 可轉換為帶時區的UTC格式（Note：帶時區與不帶時區的datetime彼此無法比較大小，故無法混用）
def str2datetime(strdate, _timezone=False):
    datetime_obj = datetime.strptime(strdate, "%Y-%m-%d")
    if _timezone:
        datetime_obj = datetime_obj.replace(tzinfo=timezone.utc)
    return datetime_obj

def datetime2str(date):
    return date.strftime("%Y-%m-%d")

# 將Unix时间戳转换为datetime
def unix_timestamp2datetime(unix_timestamp):
    if isinstance(unix_timestamp, str):
        unix_timestamp = int(unix_timestamp)
    return datetime.fromtimestamp(unix_timestamp)

def convert_objectid_to_str(data):
    if isinstance(data, dict):
        return {key: convert_objectid_to_str(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_objectid_to_str(element) for element in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data

# 將本日的日期以字串形式表達，方便調用
TODAY_DATE_STR = datetime2str(datetime.today())

# Redis的哈希结构只支持存储字符串、整数和浮点数等基本数据类型，而不支持布尔值。将会话数据存储到Redis之前，将布尔值转换为字符串或整数。
def convert_session_data(session_data):
    """Convert session data to Redis compatible format."""
    converted = {}
    for key, value in session_data.items():
        if isinstance(value, bool):
            converted[key] = int(value)  # 将布尔值转换为整数（0或1）
        else:
            converted[key] = value
    return converted


# 將 UTC 時間轉換為當地時間 (假設當地是 Asia/Taipei)
local_timezone = pytz.timezone('Asia/Taipei')