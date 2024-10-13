from flask import request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from bson import ObjectId
from app.utils.mongodb_tools import MDB_client
from app.utils.alphahelix_database_tools import pool_list_db

# 引入權限設定

from . import main

@main.route("/set_user_setting", methods=['POST'])
@login_required
def set_user_setting():
    if request.form:
        new_readwise_token = request.form.get("readwise_token", '')
        # 針對user的checkbox設置是否寄信
        raw_send_report_to_email = request.form.get("send_report_to_email", '')
        send_report_to_email = False
        if raw_send_report_to_email == "yes":
            send_report_to_email = True
        
        MDB_client["users"]["user_basic_info"].update_one(
            {"_id": ObjectId(current_user.get_id())},
            {"$set": {"readwise_token": new_readwise_token,
                      "send_report_to_email": send_report_to_email}},
            upsert=True
        )
        flash("User setting updated successfully!", "success")

    return redirect(url_for("main.show_user_setting"))

@main.route('/show_user_setting')
@login_required
def show_user_setting():
    user_id = current_user.get_id()
    user_info_dict = MDB_client["users"]["user_basic_info"].find_one({"_id" : ObjectId(user_id)})
    readwise_token = user_info_dict.get("readwise_token", '')
    send_report_to_email = user_info_dict.get("send_report_to_email", '')
    employee_id = user_info_dict.get("employee_id", '')
    
    # 顯示用戶已經看過的報告數量
    user_viewed_report_meta_list = pool_list_db.get_user_viewed_reports(user_id=user_id)
    user_viewed_report_num = len(user_viewed_report_meta_list)
    
    context = {
        "readwise_token": readwise_token,
        "send_report_to_email": send_report_to_email,
        "employee_id": employee_id,
        "user_viewed_report_num": user_viewed_report_num,
    }
    return render_template("user_setting.html", **context)

@main.route('/new_user_register')
@login_required
#@system_edit_perm.require(http_exception=403)
def new_user_register():
    return redirect(url_for("auth.user_register"))