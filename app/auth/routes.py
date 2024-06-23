from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_user, current_user, logout_user
from flask_principal import Principal, Permission, RoleNeed, Identity, identity_changed, identity_loaded, AnonymousIdentity
from flask import current_app as app
from app.utils.mongodb_client import MDB_client
from app import bcrypt
from .forms import RegistrationForm, LoginForm
from .users_model import User
from pymongo import ObjectId

from . import auth  # 从当前包中导入 main 蓝图

@auth.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.check_username_exist(form.username.data):
            flash('Your username already exist!', 'danger')
            return redirect(url_for('auth.register'))
        
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password_hash=hashed_password)
        user.create()
        flash('Your account has been created!', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html', title='Register', form=form)
                     
@auth.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user_data = MDB_client["users"]["user_basic_info"].find_one({"username": form.username.data})
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], form.password.data):
            user = User.get(user_data['_id'])
            login_user(user, remember=form.remember.data)
            # 取得用戶的權限設置
            identity_changed.send(app._get_current_object(), identity=Identity(user.get_id()))
            return redirect(url_for('main.dashboard'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', form=form)

@auth.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/change_password', methods=['POST'])
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
            # {"$set": {"test": news_hashed_password}},
            # upsert=True
        )
        flash('密碼修改成功！', 'success')
        return redirect(url_for('main.render_static_html', page='change_password'))
    
    return redirect(url_for('main.render_static_html', page='change_password'))