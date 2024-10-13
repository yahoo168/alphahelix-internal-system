import re
import pytz

from flask import request, jsonify, render_template, redirect, url_for, flash, session, g
from bson import ObjectId
from app.utils.mongodb_tools import MDB_client
from app.utils.utils import *
from app import cache

from . import main

@main.before_request
def _check_notifications_before_request():
    """在每次請求之前執行，獲取用戶的通知"""
    if '_user_id' in session:  # 假設用戶ID保存在session中
        g.undisplayed_notification_num, g.recent_notification_meta_list = _get_recent_notifications(user_id=session['_user_id'])
    else:
        g.recent_notification_meta_list = []

@main.route('/notifications_recent/<user_id>', methods=['GET'])
def _get_recent_notifications(user_id, num_limit=10):
    """取得用戶未讀取的通知"""
    collection = MDB_client["users"]["notifications"]
    undisplayed_notification_num = len(list(collection.find({"user_id": ObjectId(user_id),
                                                            "is_displayed": False})))
                                                                            
    recent_notification_meta_list = list(collection.find({"user_id": ObjectId(user_id)},
                                                        sort=[("upload_timestamp", -1)],
                                                        limit=num_limit))
    for item_meta in recent_notification_meta_list:
        item_meta["_id"] = str(item_meta["_id"])
        # item_meta["upload_timestamp"] = item_meta["upload_timestamp"].replace(tzinfo=ZoneInfo('UTC')).astimezone(local_tz)
        timestamp = item_meta["upload_timestamp"]
        # 加入 UTC 時區資訊後，轉換為當地時間
        local_timestamp = pytz.utc.localize(timestamp).astimezone(local_timezone)
        item_meta["upload_timestamp"] = local_timestamp.strftime('%Y-%m-%d %H:%M')
        item_meta["message"] = re.sub(r'<[^>]*>', '', item_meta["message"])
    
    return undisplayed_notification_num, recent_notification_meta_list

# http://127.0.0.1:5000/main/notification_detail/670761bb601714b91e72c408
@main.route('/notification_detail/<notification_id>', methods=['GET'])
def notification_detail(notification_id):
    notification_meta = MDB_client["users"]["notifications"].find_one({"_id": ObjectId(notification_id)})
    # 若取得通知資訊，則將通知標示為已讀取，並顯示通知詳細資訊
    if notification_meta is not None:
        mark_notification_as_read(notification_id)
        # 除去多餘的不可見字符和換行符
        notification_text = re.sub(r'[\r\t]+', '', notification_meta['message']).strip()
        # 
        notification_text = notification_text.replace('\n', '')
        # # 將連續3個以上的換行符替換為2個<br>
        # notification_text = re.sub(r'\n{3,}', '<br><br>', notification_text)
        # notification_text = re.sub(r'\n{2}', '<br>', notification_text)
        # # 將剩餘的換行符（單獨出現）替換為''，（避免在HTML中出現多餘的空行或<br>）
        notification_meta['message'] = notification_text
        
        return render_template("notification_detail.html", notification_meta=notification_meta)
    else:
        return render_template("404.html"), 404
        #notification_meta['message'] = re.sub(r'(<br\s*/?>){3,}', '<br><br>', notification_meta['message'])

@main.route('/notifications_all/<user_id>', methods=['GET'])
def get_all_notifications(user_id):
    """取得用戶未讀取的通知"""
    collection = MDB_client["users"]["notifications"]
                                                                            
    notification_meta_list = list(collection.find({"user_id": ObjectId(user_id)},
                                                    sort=[("upload_timestamp", -1)]
                                                ))
    
    for notification_meta in notification_meta_list:
        # 控制datetime，仅显示日期和时间（精确到分钟）
        timestamp = notification_meta["upload_timestamp"]
        local_timestamp = pytz.utc.localize(timestamp).astimezone(local_timezone)
        notification_meta["upload_timestamp"] = local_timestamp.strftime('%Y-%m-%d %H:%M')
        notification_meta["type"] = notification_meta["type"].title()
    
    context = {
        "notification_meta_list": notification_meta_list,
    } 
    
    return render_template("notifications_overview.html", **context)

@main.route('/notifications/display/<user_id>', methods=['POST'])
def mark_notification_as_displayed(user_id):
    """將指定用戶的通知標示為已展示"""
    MDB_client["users"]["notifications"].update_many(
        {"user_id": ObjectId(user_id), "is_displayed": False},
        {"$set": {"is_displayed": True}}
    )
    return jsonify({"status": "success"}), 200 

@main.route('/notifications/read/<notification_id>', methods=['POST'])
def mark_notification_as_read(notification_id):
    """將指定的通知標示為已讀取"""
    result = MDB_client["users"]["notifications"].update_one(
        {"_id": ObjectId(notification_id)},
        {"$set": {"is_read": True}}
    )
    if result.matched_count > 0:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", "message": "Notification not found"}), 404

