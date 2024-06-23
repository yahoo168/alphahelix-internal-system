from datetime import datetime, timezone
from bson import ObjectId

def _is_valid_date(date_string):
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def _is_pdf_file(file_name):
    file_type = file_name[-4:]
    return file_type == ".pdf"

def is_valid_report_name(file_name):
    if _is_valid_date(file_name[:10]) and _is_pdf_file(file_name):
        return True
    else:
        return False

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