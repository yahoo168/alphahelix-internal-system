from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
import secrets
from flask_principal import Principal, Permission, RoleNeed, UserNeed, Identity, identity_changed, identity_loaded, AnonymousIdentity
from flask_login import current_user

bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = "auth.login"  # 设置登录视图的端点
login_manager.login_message_category = 'info'  # 设置闪现消息的类别

def print_registered_routes(app, blueprint_name):
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(blueprint_name + "."):
            methods = ','.join(rule.methods)
            print(f"{rule.endpoint}: {methods} {rule}")

def create_app():
    app = Flask(__name__)
    # 为了确保安全性，SECRET_KEY 应该是随机生成的并且足够复杂。你可以使用 Python 的 secrets
    app.config["SECRET_KEY"] = secrets.token_hex(16)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    principals = Principal(app)

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
    app.config['FUNDAMENTAL_PERMISSION'] = Permission(RoleNeed('user_fundamental'))
    # 可以訪問量化研究相關頁面
    app.config['QUANT_PERMISSION'] = Permission(RoleNeed('user_quant'))
    # 只能訪問限定的試用頁面
    app.config['TRIAL_ACCOUNT_PERMISSION'] = Permission(RoleNeed('user_trial_account'))
    
    # 設置身份加載時的角色處理程序
    @identity_loaded.connect_via(app)
    def on_identity_loaded(sender, identity):
        identity.user = current_user
        if hasattr(current_user, 'roles'):
            # 把用戶權限（roloes）加載到用戶資訊中
            identity.provides.add(RoleNeed(current_user.roles))
    
    return app
        
    # 打印所有路由信息到控制台
    # with app.app_context():
    #     for rule in app.url_map.iter_rules():
    #         methods = ','.join(rule.methods)
    #         print(f"{rule.endpoint}: {methods} {rule}")