# app/auth/__init__.py
from flask import Blueprint

utils = Blueprint('utils', __name__)

from app.utils import mongodb_client
from app.utils import utils

# 暫時使用絕對路徑引用
import sys, os

# 获取需要导入模块的路径
# module_path = os.path.join("/Users/yahoo168/Desktop/資料庫_測試功能/alphahelix-database-cloud/")

# # 将模块路径添加到 sys.path
# if module_path not in sys.path:
#     sys.path.append(module_path)

from external_tools import google_tools
from external_tools import readwise_tools
# from external_tools import google_tools #type: ignore
# from external_tools import readwise_tools  #type: ignore

# 导出 google_tools 模块
# __all__ = ['google_tools', 'readwise_tools']