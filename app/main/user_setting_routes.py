from flask import request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from bson import ObjectId
from app.utils.mongodb_tools import MDB_client
from app import system_edit_perm

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
    user_info_dict = MDB_client["users"]["user_basic_info"].find_one({"_id" : ObjectId(current_user.get_id())})
    readwise_token = user_info_dict.get("readwise_token", '')
    send_report_to_email = user_info_dict.get("send_report_to_email", '')
    employee_id = user_info_dict.get("employee_id", '')
    
    context = {
        "readwise_token": readwise_token,
        "send_report_to_email": send_report_to_email,
        "employee_id": employee_id,
    }
    return render_template("user_setting.html", **context)

@main.route('/new_user_register')
@login_required
@system_edit_perm.require(http_exception=403)
def new_user_register():
    return redirect(url_for("auth.user_register"))