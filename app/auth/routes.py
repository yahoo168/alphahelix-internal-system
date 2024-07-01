from flask import request, redirect, url_for, flash, render_template, session
from flask_login import login_required, login_user, current_user, logout_user
from flask_principal import Identity, identity_changed, AnonymousIdentity
from flask_wtf.csrf import generate_csrf
from flask import current_app as app
from .forms import RegistrationForm, LoginForm
from bson import ObjectId
import logging
import secrets

from app.utils.mongodb_tools import MDB_client
from app import bcrypt

from .users_model import User, check_username_exist, create_new_user, load_user

from flask import jsonify

from . import auth  # 从当前包中导入 auth blueprint

# setting logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# # 使用 before_app_request 在应用第一次请求之前初始化权限。
# @auth.before_app_request
# def before_request():        
#     # 为每个请求设置一个CSRF令牌（目前关闭CSRF保护）
#     if '_csrf_token' not in session:
#         session['_csrf_token'] = generate_csrf()

# 在每个应用程序上下文结束时标记会话为已修改，从而确保会话数据在请求处理结束后被正确保存。
@auth.teardown_app_request
def teardown(exception):
    try:
        session.modified = True
    except Exception as e:
        logger.error(f"Error during session teardown: {e}")

# 确保浏览器不缓存页面，保证每次访问页面时都从服务器获取最新的内容。
@auth.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
    return response

@auth.route("/user_register", methods=['GET', 'POST'])
def user_register():
    form = RegistrationForm()
    if form.validate_on_submit():
        if check_username_exist(form.username.data):
            flash('Username already exist!', 'danger')
            return redirect(url_for('auth.register'))
        
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        create_new_user(email=form.email.data, username=form.username.data, password_hash=hashed_password, roles=form.roles.data)
        flash('New account has been created!', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('user_register.html', title='Register', form=form)
              
@auth.route("/login", methods=['GET', 'POST'])
def login():
    # 如果用戶已經登錄，則重定向到主頁
    if current_user.is_authenticated:
        flash("You have logined.", category="info")
        logging.info(f'User {current_user.username} already logged in')
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user_data = MDB_client["users"]["user_basic_info"].find_one({"username": form.username.data})
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], form.password.data):
            user = User.get(user_data['_id'])
            # 清理舊的session，以避免數據錯誤
            session.clear()
            # 如果值为 True，那么会在用户浏览器中写入一个长期有效的 cookie，使用这个 cookie 可以复现用户会话。cookie 默认记住一年
            login_user(user, remember=form.remember.data)
            session['session_id'] = secrets.token_hex(16)  # 生成唯一會話ID
            session['user_id'] = user.get_id() # 保存用戶ID
            
            # 取得用戶的權限設置
            identity_changed.send(app._get_current_object(), identity=Identity(user.get_id()))
            logger.info(f'User {user.username} logged in successfully')
            return redirect(url_for('main.dashboard'))
        else:
            logger.info(f'logging fail')
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', form=form)

@auth.route("/logout")
@login_required
def logout():
    logout_user()
    # 通知 Flask-Principal 系統用戶的身份已經變更，將當前用戶的身份設置為匿名身份
    identity_changed.send(app._get_current_object(), identity=AnonymousIdentity())
    session.clear()  # 清理session
    return redirect(url_for('auth.login'))

@auth.route('/change_password', methods=['POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_user_id = current_user.get_id()
        original_password = request.form['original_password']
        user_data = MDB_client["users"]["user_basic_info"].find_one({"_id": ObjectId(current_user_id)})
        if not bcrypt.check_password_hash(user_data['password_hash'], original_password):
            flash('舊密碼輸入錯誤', "danger")
            return redirect(url_for('main.render_static_html', page='change_password'))
        
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('新密碼和確認密碼不匹配！', 'danger')
            return redirect(url_for('main.render_static_html', page='change_password'))
        
        news_hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        MDB_client["users"]["user_basic_info"].update_one(
            {"_id": ObjectId(current_user_id)},
            {"$set": {"password_hash": news_hashed_password}},
        )
        flash('密碼修改成功，請重新登入！', 'success')
        logout_user()
        # 通知 Flask-Principal 系統用戶的身份已經變更。具體來說，這行代碼會將當前用戶的身份設置為匿名身份
        identity_changed.send(app._get_current_object(), identity=AnonymousIdentity())
        return redirect(url_for('auth.login'))
    
    return redirect(url_for('main.render_static_html', page='change_password'))