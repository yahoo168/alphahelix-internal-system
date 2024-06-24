from flask import request, redirect, url_for, flash, render_template, session
from flask_login import login_required, login_user, current_user, logout_user
from flask_principal import Identity, identity_changed, AnonymousIdentity
from flask import current_app as app
from .forms import RegistrationForm, LoginForm
from bson import ObjectId
import logging
import secrets
from app.utils.mongodb_client import MDB_client
from app import bcrypt
from .users_model import User, check_username_exist, create_new_user

from . import auth  # 从当前包中导入 auth blueprint

# setting logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@auth.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        if check_username_exist(form.username.data):
            flash('Your username already exist!', 'danger')
            return redirect(url_for('auth.register'))
        
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        create_new_user(email=form.email.data, username=form.username.data, password_hash=hashed_password)
        # user = User(username=form.username.data, email=form.email.data, password_hash=hashed_password)
        flash('New account has been created!', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html', title='Register', form=form)
              
@auth.route("/login", methods=['GET', 'POST'])
def login():
    # 如果用戶已經登錄，則重定向到主頁
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user_data = MDB_client["users"]["user_basic_info"].find_one({"username": form.username.data})
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], form.password.data):
            user = User.get(user_data['_id'])
            login_user(user, remember=form.remember.data)
            session['session_id'] = secrets.token_hex(16)  # 生成唯一會話ID
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
        # 清理當前session並登出用戶
        logout_user()
        session.clear()
        # 通知 Flask-Principal 系統用戶的身份已經變更。具體來說，這行代碼會將當前用戶的身份設置為匿名身份
        identity_changed.send(app._get_current_object(), identity=AnonymousIdentity())
        return redirect(url_for('auth.login'))
    
    return redirect(url_for('main.render_static_html', page='change_password'))