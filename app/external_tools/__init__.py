# app/auth/__init__.py
from flask import Blueprint

external_tools = Blueprint('external_tools', __name__)

from app.external_tools import mongodb_tools
from app.external_tools import utils

# 暫時使用絕對路徑引用
import sys, os

# 获取需要导入模块的路径
module_path = os.path.join("/Users/yahoo168/Desktop/資料庫_測試功能")

# 将模块路径添加到 sys.path
if module_path not in sys.path:
    sys.path.append(module_path)

# 现在可以导入 external_modules 目录下的模块
from self_finance_database_tool_cloud import google_tools # type: ignore

# 导出 google_tools 模块
__all__ = ['google_tools', 'readwise_tools']