# app.py
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import akshare as ak
from datetime import datetime, timedelta
import hashlib
import requests
from celery import Celery

app = Flask(__name__)
app.config.update({
    'SQLALCHEMY_DATABASE_URI': 'mysql+pymysql://:stock_uesr:password1@localhost/stock_db',
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'JWT_SECRET_KEY': 'ps15075356735',
    'WECHAT_APPID': 'wx935c29bf7f27f59b',
    'WECHAT_SECRET': '4539c37b86d00655a31825a590d51fd2'
})

# 初始化扩展
db = SQLAlchemy(app)
jwt = JWTManager(app)
celery = Celery(app.name, broker='redis://localhost:6379/0')

# 数据库模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    openid = db.Column(db.String(128), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

class UserStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    code = db.Column(db.String(10), index=True)
    name = db.Column(db.String(50))
    added_at = db.Column(db.DateTime, default=datetime.now)

class NewsCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_code = db.Column(db.String(10), index=True)
    title = db.Column(db.Text)
    content_hash = db.Column(db.String(32), unique=True)
    publish_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)

# 微信登录接口
@app.route('/api/auth/login', methods=['POST'])
def login():
    code = request.json.get('code')
    wx_url = f"https://api.weixin.qq.com/sns/jscode2session?appid={app.config['WECHAT_APPID']}&secret={app.config['WECHAT_SECRET']}&js_code={code}&grant_type=authorization_code"
    
    res = requests.get(wx_url).json()
    if 'openid' not in res:
        return jsonify({'code': 401, 'msg': '登录失败'}), 401

    # 创建或获取用户
    user = User.query.filter_by(openid=res['openid']).first()
    if not user:
        user = User(openid=res['openid'])
        db.session.add(user)
        db.session.commit()

    # 生成JWT
    access_token = create_access_token(identity=user.id)
    return jsonify({
        'token': access_token,
        'user_id': user.id
    })

# 股票管理接口
@app.route('/api/stocks', methods=['GET', 'POST'])
@jwt_required()
def manage_stocks():
    user_id = get_jwt_identity()
    
    if request.method == 'POST':
        data = request.json
        # 验证股票代码有效性
        stock_info = ak.stock_individual_info_em(symbol=data['code'])
        if stock_info.empty:
            return jsonify({'code': 400, 'msg': '无效股票代码'}), 400

        # 添加自选股
        new_stock = UserStock(
            user_id=user_id,
            code=data['code'],
            name=stock_info.iloc[0]['股票简称']
        )
        db.session.add(new_stock)
        db.session.commit()
        return jsonify({'code': 0})

    # 获取自选股列表
    stocks = UserStock.query.filter_by(user_id=user_id).all()
    return jsonify([{
        'code': s.code,
        'name': s.name
    } for s in stocks])

# 新闻接口
@app.route('/api/news')
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

# 定时任务配置
@celery.task
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
                "template_id": "你的模板ID",
                "data": {
                    "thing1": {"value": "今日股票资讯更新"},
                    "time2": {"value": datetime.now().strftime("%H:%M")},
                    "thing3": {"value": content[:20] + "..."}
                }
            }
        )

def get_wechat_token():
    """获取微信access_token"""
    res = requests.get(
        f'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app.config["WECHAT_APPID"]}&secret={app.config["WECHAT_SECRET"]}'
    )
    return res.json().get('access_token')

if __name__ == '__main__':
    db.create_all()
    app.run(host='0.0.0.0', port=8000)