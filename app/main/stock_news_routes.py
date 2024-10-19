from flask import request, jsonify, render_template, redirect, url_for, flash, send_file
from flask import current_app as app
from flask_login import login_required, current_user

import pandas as pd
import re

from datetime import datetime, timedelta, timezone
from bson import ObjectId

from app.utils.mongodb_tools import MDB_client
from app.utils.utils import *
from app.utils.alphahelix_database_tools import pool_list_db

from app import redis_instance
# 引入權限設定
from app import portfolio_info_access_role
from app import ticker_setting_perm, issue_setting_perm
from app import cache

from . import main

@main.route("/ticker_news_review", methods=['GET', 'POST'])
def ticker_news_review():
    ticker = request.form.get('ticker')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    start_timestamp = str2datetime(start_date)
    end_timestamp = str2datetime(end_date)
    
    news_meta_list = list(MDB_client["preprocessed_content"]["stock_news_summary"].find({"ticker": ticker, "data_timestamp": {"$gte": start_timestamp, "$lte": end_timestamp}
                                                                                                }, sort=[("data_timestamp", -1)], projection={"_id": 0, "ticker": 1, "data_timestamp": 1, "content": 1}))
    
    for item_meta in news_meta_list:
        item_meta["date"] = datetime2str(item_meta["data_timestamp"])
        
    return render_template("ticker_news_review.html", ticker=ticker, start_date=start_date, end_date=end_date, item_meta_list=news_meta_list)

@main.route("/ticker_news_overview", methods=['GET', 'POST'])
@login_required
def ticker_news_overview():
    # 取得用戶的追蹤股票列表
    following_ticker_list = pool_list_db.get_following_ticker_list(user_id=ObjectId(current_user.get_id()))
    
    # 取得用戶追蹤股票的新聞摘要
    end_timestamp = datetime.now(timezone.utc)
    start_timestamp = end_timestamp - timedelta(days=14)

    raw_news_meta_list = list(MDB_client["preprocessed_content"]["stock_news_summary"].find({"ticker": {"$in": following_ticker_list}, "data_timestamp": {"$gte": start_timestamp, "$lte": end_timestamp}
                                                                                                }, sort=[("data_timestamp", -1)], projection={"_id": 0, "ticker": 1, "data_timestamp": 1, "content": 1}))
    if len(raw_news_meta_list) > 0:
        # 使用 groupby('data_timestamp') 按照 data_timestamp 进行分组、使用 apply 函数对每个分组创建一个字典，将 ticker 作为键，content 作为值。
        # 使用 to_dict() 方法将结果转换为字典格式。
        news_summary_meta_list = pd.DataFrame(raw_news_meta_list).groupby('data_timestamp').apply(
            lambda group: {
                "data_timestamp": group['data_timestamp'].iloc[0],
                "content": dict(zip(group['ticker'], group['content']))
            }).tolist()

        news_summary_meta_list.sort(key=lambda x: x['data_timestamp'], reverse=True)
        
        url_pattern = re.compile(r'https?://\S+') # 定義正則表達式來匹配URL
        weekday_list = ['(一)', '(二)', '(三)', '(四)', '(五)', '(六)', '(日)']
        for item_meta in news_summary_meta_list:    
            # 去除 URL 並計算所有新聞的總字數
            word_count = sum(len(url_pattern.sub('', news)) for news in item_meta["content"].values())
            item_meta["read_mins"] = str(round(word_count / 1000, 1)) + " mins"
            # 格式化日期字符串
            date_str = datetime2str(item_meta['data_timestamp'])
            weekday_str = weekday_list[item_meta['data_timestamp'].weekday()]
            # 用於id定位（ticker導引列）
            item_meta["date_str"] = date_str
            # 用於前端顯示（包含星期）
            item_meta["date_with_weekday"] = f"{date_str} {weekday_str}"
        
    # 若無新聞，則返回空列表（避免報錯）
    else:
        news_summary_meta_list = []
        
    return render_template("ticker_news_overview.html", item_meta_list=news_summary_meta_list)