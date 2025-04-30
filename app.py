# app.py
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from celery import Celery
import os
from dotenv import load_dotenv
from datetime import datetime

# --------------------------------------------------------------------
# 1) 读取 .env（必须放在任何用到 os.getenv 之前）
# --------------------------------------------------------------------
load_dotenv()          # 默认从当前目录或父目录查找 .env

# --------------------------------------------------------------------
# 2) 创建 Flask，并用环境变量配置
# --------------------------------------------------------------------
app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URI"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY"),

    # 微信相关
    WECHAT_APPID=os.getenv("WECHAT_APPID"),
    WECHAT_SECRET=os.getenv("WECHAT_SECRET"),
    WECHAT_TEMPLATE_ID=os.getenv("WECHAT_TEMPLATE_ID"),
)

# --------------------------------------------------------------------
# 3) 初始化扩展
# --------------------------------------------------------------------
from models import db
db.init_app(app)

jwt = JWTManager(app)

# Celery 仍然用 Redis，但地址从 env 取
celery = Celery(
    app.import_name,
    broker=os.getenv("REDIS_BROKER_URL"),
)
celery.conf.update(app.config)   # 如果你想让 Celery 也能拿到 app.config

# 注册所有路由
from routes import init_routes
init_routes(app)

# 注册Celery任务
from routes.news import daily_news_job

@celery.task
def run_daily_news_job():
    """Celery任务包装器"""
    with app.app_context():
        daily_news_job()

# 根目录
@app.route('/', methods=['GET'])
def server_info():
    return jsonify({
        'project': 'Stock API Service',
        'version': '1.0.0',
        'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# /api - 返回API服务状态
@app.route('/api', methods=['GET'])
def api_status():
    return jsonify({'status': 'running'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=9999, debug=True)
