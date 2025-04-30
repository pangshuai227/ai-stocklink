from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# 初始化SQLAlchemy，但不传入app实例（将在app.py中完成）
db = SQLAlchemy()

# 数据库模型
class User(db.Model):
    __tablename__ = 'users'  # 规范表名加s
    id = db.Column(db.Integer, primary_key=True)
    openid = db.Column(db.String(128), unique=True, nullable=False, index=True)  # 必须唯一且加索引
    session_key = db.Column(db.String(255), nullable=True)  # 可以为空，因过期需要换
    unionid = db.Column(db.String(128), nullable=True, index=True)  # 有可能没有
    nickname = db.Column(db.String(64), nullable=True)  # 用户昵称（预留）
    avatar_url = db.Column(db.String(255), nullable=True)  # 用户头像（预留）
    role = db.Column(db.String(20), default='user')  # 用户角色：user/admin等
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系：用户有多个自选股
    stocks = db.relationship('UserStock', backref='user', lazy=True)

class UserStock(db.Model):
    __tablename__ = 'user_stocks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    code = db.Column(db.String(10), index=True, nullable=False)  # 股票代码
    name = db.Column(db.String(50), nullable=True)  # 股票名称
    added_at = db.Column(db.DateTime, default=datetime.now)

class NewsCache(db.Model):
    __tablename__ = 'news_cache'
    id = db.Column(db.Integer, primary_key=True)
    stock_code = db.Column(db.String(10), index=True, nullable=False)
    title = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(32), unique=True, nullable=False)  # 内容哈希，防重复
    publish_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
