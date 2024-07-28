from flask import Flask, request, render_template, redirect, url_for, session
from flask_bcrypt import Bcrypt
# from flask_session import Session
from flask_login import LoginManager
from flask_principal import Principal, identity_changed, identity_loaded, AnonymousIdentity, Permission, RoleNeed, UserNeed, PermissionDenied
from flask_login import current_user
from flask_wtf import CSRFProtect
from flask_caching import Cache
import redis

import os, logging
import secrets
from datetime import timedelta
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = "rediss://:pbd1c919e60c9b9e06d1319c520f313a722c6eb9e319dbc8dfcc19497c40397bb@ec2-44-214-29-16.compute-1.amazonaws.com:9029"
url = urlparse(REDIS_URL)

# 使用 ConnectionPool 建立连接池
pool = redis.ConnectionPool(
    host=url.hostname,
    port=url.port,
    password=url.password,
    connection_class=redis.SSLConnection,
    # 禁用 SSL 證書驗證，避免錯誤
    ssl_cert_reqs=None
)

# 使用连接池建立 Redis 连接
redis_instance = redis.Redis(connection_pool=pool)

# 創建擴展實例
bcrypt = Bcrypt()
login_manager = LoginManager()
principals = Principal()
# 產生CSRF token
csrf = CSRFProtect()
# 用於緩存的全局變數
cache = Cache()

# 定義功能權限
us_data_view_perm = Permission(RoleNeed('us_data_view'))
us_data_upload_perm = Permission(RoleNeed('us_data_upload'))
us_data_edit_perm = Permission(RoleNeed('us_data_edit'))

tw_data_view_perm = Permission(RoleNeed('tw_data_view'))
tw_data_upload_perm = Permission(RoleNeed('tw_data_upload'))
tw_data_edit_perm = Permission(RoleNeed('tw_data_edit'))

quant_data_view_perm = Permission(RoleNeed('quant_data_view'))
quant_data_upload_perm = Permission(RoleNeed('quant_data_upload'))
quant_data_edit_perm = Permission(RoleNeed('quant_data_edit'))

administation_data_view_perm = Permission(RoleNeed('administation_data_view'))
administation_data_upload_perm = Permission(RoleNeed('administation_data_upload'))
administation_data_edit_perm = Permission(RoleNeed('administation_data_edit'))

system_edit_perm = Permission(RoleNeed('system_edit'))

def create_app():
    app = Flask(__name__)
    # 從環境變數中讀取Session的安全密鑰，如果沒有則使用隨機生成的16進位字符串（本地測試用）
    app.config["SECRET_KEY"] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    
    # server side session(配置Session，並存儲到Redis)
    # app.config['SESSION_TYPE'] = 'redis'
    
    # 配置Session，並使用簽名的Cookie儲存
    # app.config['SESSION_TYPE'] = 'filesystem'
    
    app.config['SESSION_PERMANENT'] = True
    app.config['SESSION_USE_SIGNER'] = True  # 確保Session不會被竄改
    
    # server side session
    # app.config['SESSION_KEY_PREFIX'] = 'session:' # 设置会话键的前綴（範例：session:2f3e1b2c4d5e6f7890a1b2c3d4e5f6a7）
    # app.config['SESSION_REDIS'] = redis_instance
    
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)  # seesion有效時間設定為1小時
    #針對Session的安全性設定
    app.config["SESSION_COOKIE_SECURE"] = True  # 確保在HTTPS下傳輸
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = 'Lax'
    app.config['WTF_CSRF_ENABLED'] = False  # 關閉CSRF保護
    
    # 配置緩存
    app.config['CACHE_TYPE'] = 'RedisCache'
    app.config['CACHE_REDIS_URL'] = REDIS_URL
    # 初始化緩存
    cache.init_app(app)
    
    # server side session
    # 初始化Session
    # Session(app)
    
    # 初始化擴展
    csrf.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.session_protection = "strong"
    login_manager.login_view = "auth.login"  # 設置登入時的endpoint
    login_manager.login_message_category = 'info'  # 設置flash的類別
    principals.init_app(app)
    
    # 在每个应用程序上下文结束时标记会话为已修改，从而确保会话数据在请求处理结束后被正确保存。
    @app.after_request
    def after_request(response):
        try:
            session.modified = True
        except Exception as e:
            logger.error(f"Error during session teardown: {e}")
        return response
    
    @app.before_request
    def before_request_ensure_session():
        session_id, session_user_id = session.get('session_id'), session.get('user_id')
        current_user_id = current_user.get_id() if current_user.is_authenticated else 'Anonymous'
        logger.info(f"Before request: session_id={session_id}, session_user_id={session_user_id}, current_user_id={current_user_id}")

        if request.endpoint in ['auth.login', 'auth.logout']:
            return

        if session_id is None or session_user_id != current_user_id:
            logger.warning("Session data is missing or invalid. Trying to restore from Redis.")
            if current_user.is_authenticated:
                return redirect(url_for('auth.logout'))
            else:
                return redirect(url_for('auth.login'))
        
        # if session_id is None or session_user_id != current_user_id:
        #     logger.warning("Session data is missing or invalid. Trying to restore from Redis.")
        #     if current_user.is_authenticated:
        #         try:
        #             redis_keys = redis_instance.keys(f'session:*')
        #             session_restored = False
        #             for redis_key in redis_keys:
        #                 if redis_instance.type(redis_key) != b'hash':
        #                     continue
        #                 session_data = redis_instance.hgetall(redis_key)
        #                 if session_data and session_data.get(b'user_id') == current_user_id.encode():
        #                     for key, value in session_data.items():
        #                         session[key.decode('utf-8')] = value.decode('utf-8') if isinstance(value, bytes) else value
        #                     logger.info(f"Session data restored from Redis: {session_data}")
        #                     session['session_id'] = redis_key.decode('utf-8').split(':')[1]
        #                     session_restored = True
        #                     break
        #             if not session_restored:
        #                 logger.warning(f"No session data found in Redis for user_id: {current_user_id}")
        #                 return redirect(url_for('auth.logout'))
        #         except Exception as e:
        #             logger.error(f"Failed to restore session from Redis: {e}")
        #             return redirect(url_for('auth.logout'))
        #     else:
        #         logger.info("User not authenticated and session data is missing.")
        #         return redirect(url_for('auth.login'))

    from app.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from app.main import main as main_blueprint
    app.register_blueprint(main_blueprint, url_prefix='/main')
    
    # load_user 是 Flask-Login 提供的一個回調函數，用於加載用戶的信息。就能夠在每個請求中管理和跟蹤當前用戶的狀態。
    from app.auth.users_model import load_user
    login_manager.user_loader(load_user)
    
    @identity_loaded.connect_via(app)
    def on_identity_loaded(sender, identity):
        identity.user = current_user
        identity.provides.add(UserNeed(current_user.get_id()))
        
        roles_permission_dict = get_roles_permission_dict()
        if hasattr(current_user, 'roles'):
            for role in current_user.roles:
                for perm in roles_permission_dict.get(role, []):
                    identity.provides.add(perm)
            logging.info(f'User {current_user.username} has roles: {current_user.roles}')
        
    # 權限錯誤處理，當用戶沒有權限時，返回403錯誤並顯示permission_denied.html
    @app.errorhandler(403)
    def handle_permission_denied(error):
        return render_template('permission_denied.html'), 403
    
    return app

def get_roles_permission_dict():    
    # 為角色分配功能權限
    role_permissions_dict = {
        "general_manager": [RoleNeed("us_data_view"), RoleNeed("us_data_upload"), 
                            RoleNeed("tw_data_view"), RoleNeed("tw_data_upload"), 
                            RoleNeed("quant_data_view"), RoleNeed("quant_data_upload"),
                            RoleNeed("admin_data_view"), RoleNeed("admin_data_upload")],
        
        "investment_manager": [RoleNeed("us_data_view"), RoleNeed("us_data_upload"), 
                               RoleNeed("tw_data_view"), RoleNeed("tw_data_upload"), 
                               RoleNeed("quant_data_view"), RoleNeed("quant_data_upload"),
                               RoleNeed("admin_data_view"), RoleNeed("admin_data_upload")],
        
        "investment_consultant": [RoleNeed("us_data_view"), RoleNeed("tw_data_view")],
        
        "investment_researcher": [RoleNeed("us_data_view"), RoleNeed("us_data_upload"), 
                                  RoleNeed("tw_data_view"), RoleNeed("tw_data_upload")],
        
        "quant_researcher": [RoleNeed("quant_data_view"), RoleNeed("quant_data_upload")],
        
        "administration_staff": [RoleNeed("admin_data_view"), RoleNeed("admin_data_upload")],
        
        "investment_intern": [RoleNeed("us_data_view"), RoleNeed("us_data_upload"), 
                                  RoleNeed("tw_data_view"), RoleNeed("tw_data_upload")],
        
        "remote_investment_intern": [RoleNeed('us_data_view'), RoleNeed('us_data_upload'), RoleNeed('us_data_edit'),
                                     RoleNeed('tw_data_view'), RoleNeed('tw_data_upload'), RoleNeed('tw_data_edit')],
        
        "tw_data_subscriber": [RoleNeed('tw_data_view')],
        
        "admin": [RoleNeed('us_data_view'), RoleNeed('us_data_upload'), RoleNeed('us_data_edit'),
                RoleNeed('tw_data_view'), RoleNeed('tw_data_upload'), RoleNeed('tw_data_edit'),
                RoleNeed('quant_data_view'), RoleNeed('quant_data_upload'), RoleNeed('quant_data_edit'),
                RoleNeed('admin_data_view'), RoleNeed('admin_data_upload'), RoleNeed('admin_data_edit'),
                RoleNeed('system_edit')],
    }
    return role_permissions_dict