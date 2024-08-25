from app.utils.readwise_tools import readwise_client
from flask import request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from bson import ObjectId
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import datetime2str, convert_objectid_to_str
from . import main

@main.route("/note_search_page")
@login_required
def note_search_page(tag_show_days=30):
    user_id = current_user.get_id()
    user_info = MDB_client["users"]["user_basic_info"].find_one({"_id": ObjectId(user_id)}, {"readwise_token": 1, "_id": 0})
    readwise_token = user_info.get("readwise_token", '')
    if readwise_token == '':
        flash("Please set Readwise token first!", "danger")
        return redirect(url_for("main.show_user_setting"))
    # 建立ReadwiseTool實例
    # 將用戶的筆記上傳至mongodb
    readwise_client.token = readwise_token
    readwise_client.upload_articles_to_MDB(user_id=user_id)
    lastest_article_date = datetime2str(readwise_client.get_lastest_article_date(user_id=user_id))
    # 取得最近（預設為30日）的tag list，以供用戶選擇
    article_meta_list = readwise_client.get_article_meta_list(user_id=user_id, days=tag_show_days)
    recent_tag_list = readwise_client.get_recent_tag_list(article_meta_list)
    
    # 回傳時，如何辨別出哪些是topic tag，哪些是stock tag？
    # stock_tag_list = sorted([tag.upper() for tag in recent_tag_list if len(tag.split("_")) == 1])
    # topic_tag_list = sorted(['_'.join(tag.split("_")[1:]).upper() for tag in recent_tag_list if len(tag.split("_")) > 1])
    
    # 將tag list排序並轉為upper case
    recent_tag_list = sorted([tag.upper() for tag in recent_tag_list])
    
    context = {
        "lastest_article_date": lastest_article_date,
        "recent_tag_list": recent_tag_list,
    }
    return render_template("note_search_page.html", **context)

# 重新加載筆記，預設天數為30天
@main.route("/note_reload")
@login_required
def note_reload(reload_days=30):
    user_id = current_user.get_id()
    # user_info = MDB_client["users"]["user_basic_info"].find_one({"_id": ObjectId(user_id)}, {"readwise_token": 1, "_id": 0})
    readwise_client.upload_articles_to_MDB(user_id=ObjectId(user_id), days=reload_days)
    return note_search_page()

@main.route("/note_search", methods=['POST'])
def note_search():
    data = request.json
    days = data.get("days")
    tag_list = data.get("tag_list")
    article_meta_list = readwise_client.get_article_meta_list(days=days)
    selected_article_meta_list = readwise_client.search_highlights_by_tags(article_meta_list, tag_list)
    selected_article_meta_list = convert_objectid_to_str(selected_article_meta_list)
    return jsonify(selected_article_meta_list)
