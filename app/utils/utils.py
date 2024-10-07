from datetime import datetime, timezone
from bson import ObjectId
import pytz

def beautify_broker_name(name):
    trans_dict = {"gs": "Goldman Sachs", 
                  "jpm": "J.P. Morgan", 
                  "citi": "Citi", 
                  "barclays": "Barclays",
                  "seeking_alpha": "Seeking Alpha",}
    
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