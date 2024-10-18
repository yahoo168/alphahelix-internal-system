# app/main/__init__.py
from flask import Blueprint

main = Blueprint('main', __name__, template_folder='templates')

from app.main import routes
from app.main import notifications_routes
from app.main import notes_routes
from app.main import upload_routes
from app.main import user_setting_routes
from app.main import gcs_document_routes
from app.main import followed_item_setting_routes
from app.main import stock_document_routes
from app.main import stock_news_routes