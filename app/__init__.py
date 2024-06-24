from flask import Flask
from flask_bcrypt import Bcrypt
from flask_session import Session
from flask_login import LoginManager
from flask_principal import Principal, Permission, RoleNeed, Identity, identity_changed, identity_loaded, AnonymousIdentity
from flask_login import current_user

import secrets
import os
import redis

# 創建擴展實例
bcrypt = Bcrypt()
login_manager = LoginManager()
principals = Principal()

def print_registered_routes(app, blueprint_name):
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(blueprint_name + "."):
            methods = ','.join(rule.methods)
            print(f"{rule.endpoint}: {methods} {rule}")

def create_app():
    app = Flask(__name__)
    # 從環境變數中讀取Session的安全密鑰，如果沒有則使用隨機生成的16進位字符串（本地測試用）
    app.config["SECRET_KEY"] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    # 配置Session，並存儲到Redis
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'session:'
    DEFAULT_REDIS_URL = "redis://:pbd1c919e60c9b9e06d1319c520f313a722c6eb9e319dbc8dfcc19497c40397bb@ec2-3-230-78-25.compute-1.amazonaws.com:9239"
    # 從環境變數中讀取REDIS_URL，如果沒有則使用預設值（本地測試用）
    app.config['SESSION_REDIS'] = redis.from_url(os.environ.get('REDIS_URL', DEFAULT_REDIS_URL))
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # seesion有效時間設定為1小時
    #針對Session的安全性設定
    app.config["SESSION_COOKIE_SECURE"] = True  # 確保在HTTPS下傳輸
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = 'Lax'
    # 初始化Session
    Session(app)
    # 初始化擴展
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.session_protection = "strong"
    login_manager.login_view = "auth.login"  # 設置登入時的endpoint
    login_manager.login_message_category = 'info'  # 設置flash的類別
    principals.init_app(app)

    from app.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from app.main import main as main_blueprint
    app.register_blueprint(main_blueprint, url_prefix='/main')

    from app.utils import utils as utils_blueprint
    from app.auth.users_model import User
    
    # load_user 是 Flask-Login 提供的一個回調函數，用於加載用戶的信息。就能夠在每個請求中管理和跟蹤當前用戶的狀態。
    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)
    
    # 定義角色權限並儲存到app.config中
    app.config['ADMIN_PERMISSION'] = Permission(RoleNeed('admin'))
    # 可以訪問除了 admin_permission 以外的所有路由
    app.config['DIRECTOR_PERMISSION'] = Permission(RoleNeed('user_director'))
    # 可以訪問基本面研究相關頁面
    app.config['FUND_MANAGER_PERMISSION'] = Permission(RoleNeed('user_fundamental'))
    # 可以訪問量化研究相關頁面
    app.config['QUANT_ANALYST_PERMISSION'] = Permission(RoleNeed('user_quant'))
    app.config['INVESTMENT_ANALYST_PERMISSION'] = Permission(RoleNeed('user_quant'))
    app.config['INVESTMENT_CONSULTANT_PERMISSIO'] = Permission(RoleNeed('user_quant'))
    # 只能訪問限定的試用頁面
    app.config['INVESTMENT_INTERN_PERMISSION'] = Permission(RoleNeed('user_trial_account'))
    
    # 設置身份加載時的角色處理程序
    @identity_loaded.connect_via(app)
    def on_identity_loaded(sender, identity):
        identity.user = current_user
        if hasattr(current_user, 'roles'):
            # 把用戶權限（roloes）加載到用戶資訊中
            identity.provides.add(RoleNeed(current_user.roles))
        
    return app