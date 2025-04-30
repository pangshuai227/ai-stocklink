# 路由模块初始化
from flask import Blueprint, Flask

def init_routes(app: Flask):
    """初始化所有路由"""
    from .user import user_bp
    from .stock import stock_bp
    from .news import news_bp
    
    # 注册蓝图
    app.register_blueprint(user_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(news_bp)
