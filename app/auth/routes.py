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
from app.utils.utils import convert_session_data
from app import bcrypt, redis_instance

from .users_model import User, check_username_exist, create_new_user

from . import auth  # 从当前包中导入 auth blueprint
from app import system_edit_perm

# setting logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# # 使用 before_app_request 在应用第一次请求之前初始化权限。
# @auth.before_app_request
# def before_request():        
#     # 为每个请求设置一个CSRF令牌（目前关闭CSRF保护）
#     if '_csrf_token' not in session:
#         session['_csrf_token'] = generate_csrf()

# 处理 GET 请求：表单初始化时通过 GET 请求返回注册页面。
# 处理 POST 请求：如果表单提交成功，首先检查用户名是否已存在，如果已存在则显示错误消息。如果用户名不存在，则对密码进行哈希处理并创建新用户。
@auth.route('/user_register', methods=['GET', 'POST'])
@login_required
@system_edit_perm.require(http_exception=403)
def user_register():
    form = RegistrationForm()

    # 处理 POST 请求
    if form.validate_on_submit():
        if check_username_exist(form.username.data):
            flash('Username already exists!', 'danger')
            return render_template('user_register.html', title='Register', form=form)

        # 创建新用户
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        create_new_user(
            email=form.email.data,
            username=form.username.data,
            password_hash=hashed_password,
            roles=form.roles.data
        )
        flash('New account has been created!', 'success')
        return redirect(url_for('auth.user_register'))  # 成功创建后可以重定向到同一页面或其他页面

    # 处理 GET 请求，或者表单验证失败的情况
    if request.method == 'POST':
        flash('New account creation failed!', 'danger')

    return render_template('user_register.html', title='Register', form=form)

              
@auth.route("/login", methods=['GET', 'POST'])
def login():    
    form = LoginForm()
    if form.validate_on_submit():
        user_data = MDB_client["users"]["user_basic_info"].find_one({"username": form.username.data})
        # 如果用戶資料存在且登入密碼正確
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], form.password.data):
            if user_data['is_active'] == False:
                flash('The account is inactive. Please contact the admin!', 'danger')
                return redirect(url_for('auth.login'))
            
            user = User.get(user_data['_id'])
            # 清理舊的session，以避免數據錯誤
            session.clear()
            # 如果remember值为True，那么会在用户浏览器中写入一个长期有效的 cookie，使用这个 cookie 可以复现用户会话。cookie 默认记住一年
            login_user(user, remember=form.remember.data)
            session['user_id'] = user.get_id() # 保存用戶ID
            # 取得用戶的權限設置
            identity_changed.send(app._get_current_object(), identity=Identity(user.get_id()))
            logger.info(f'User {user.username} logged in successfully')
            
            # 获取 'next' 参数 (待改：似乎沒有作用)
            next_page = request.args.get('next')
            # 如果 'next' 存在则重定向，否则重定向到默认的 dashboard
            return redirect(next_page or url_for('main.dashboard'))
        
        # 如果用戶不存在或密碼錯誤，顯示錯誤信息
        else:
            logger.info(f'logging fail')
            flash('Login Unsuccessful. Please check email and password', 'danger')
            return redirect(url_for('auth.login'))
        
    return render_template('login.html', form=form)

@auth.route("/logout")
@login_required
def logout():
    user_id = session.get('user_id')
    # 清理session
    session.clear()
    logger.info(f'User {user_id} logged out')
    # 注销用户
    logout_user()
    # 通知 Flask-Principal 系统用户的身份已经变更，将当前用户的身份设置为匿名身份
    identity_changed.send(app._get_current_object(), identity=AnonymousIdentity())
    
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