from flask import Blueprint, jsonify, current_app as app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import hashlib
import requests
import akshare as ak

from models import db, User, UserStock, NewsCache

# 创建蓝图
news_bp = Blueprint('news', __name__, url_prefix='/api')

# 新闻接口
@news_bp.route('/news')
@jwt_required()
def get_news():
    user_id = get_jwt_identity()
    user_stocks = [s.code for s in UserStock.query.filter_by(user_id=user_id).all()]
    
    news = NewsCache.query.filter(
        NewsCache.stock_code.in_(user_stocks),
        NewsCache.publish_time > datetime.now() - timedelta(days=1)
    ).order_by(NewsCache.publish_time.desc()).limit(20)
    
    return jsonify([{
        'title': n.title,
        'time': n.publish_time.strftime('%Y-%m-%d %H:%M'),
        'code': n.stock_code
    } for n in news])

# 抓取新闻任务（不是路由但与新闻相关）
def daily_news_job():
    """每日新闻抓取任务"""
    all_codes = db.session.query(UserStock.code).distinct().all()
    
    for code in all_codes:
        try:
            df = ak.stock_news_em(symbol=code)
            for _, row in df.iterrows():
                content_hash = hashlib.md5(row['内容'].encode()).hexdigest()
                if NewsCache.query.filter_by(content_hash=content_hash).first():
                    continue
                
                news = NewsCache(
                    stock_code=code,
                    title=row['标题'],
                    content_hash=content_hash,
                    publish_time=datetime.strptime(row['发布时间'], '%Y-%m-%d %H:%M:%S')
                )
                db.session.add(news)
            db.session.commit()
        except Exception as e:
            app.logger.error(f"抓取失败 {code}: {str(e)}")
    
    # 触发推送
    send_push_notifications()

def send_push_notifications():
    """发送微信推送"""
    users = User.query.all()
    for user in users:
        stocks = UserStock.query.filter_by(user_id=user.id).all()
        if not stocks:
            continue
        
        # 获取最新5条新闻
        news = NewsCache.query.filter(
            NewsCache.stock_code.in_([s.code for s in stocks]),
            NewsCache.publish_time > datetime.now() - timedelta(hours=12)
        ).order_by(NewsCache.publish_time.desc()).limit(5)
        
        # 构造消息内容
        content = "\n".join([f"▪️ {n.title}" for n in news])
        
        # 调用微信接口
        access_token = get_wechat_token()
        requests.post(
            'https://api.weixin.qq.com/cgi-bin/message/subscribe/send',
            json={
                "touser": user.openid,
                "template_id": app.config['WECHAT_TEMPLATE_ID'],
                "data": {
                    "thing1": {"value": "今日股票资讯更新"},
                    "time2": {"value": datetime.now().strftime("%H:%M")},
                    "thing3": {"value": content[:20] + "..."}
                }
            }
        )

def get_wechat_token():
    """获取微信 access_token"""
    params = {
        'grant_type': 'client_credential',
        'appid': app.config['WECHAT_APPID'],
        'secret': app.config['WECHAT_SECRET']
    }
    res = requests.get('https://api.weixin.qq.com/cgi-bin/token', params=params, timeout=5)
    return res.json().get('access_token')
