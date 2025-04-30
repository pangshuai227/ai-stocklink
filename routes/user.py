from flask import Blueprint, jsonify, request, current_app as app
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
import requests
from datetime import datetime, timedelta

from models import db, User, UserStock

# 创建蓝图
user_bp = Blueprint('user', __name__, url_prefix='/api')

# 微信登录接口
@user_bp.route('/auth/login', methods=['POST'])
def login():
    try:
        # 验证请求数据
        data = request.json
        if not data or 'code' not in data or not data.get('code'):
            return jsonify({'code': 400, 'msg': '缺少必要参数code'}), 400
            
        code = data.get('code')
        app.logger.info(f"微信登录请求，code: {code[:10]}...")
        
        # 构建微信API请求
        wx_url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            'appid': app.config.get('WECHAT_APPID'),
            'secret': app.config.get('WECHAT_SECRET'),
            'js_code': code,
            'grant_type': 'authorization_code'
        }
        
        # 记录环境变量检查（不含敏感信息）
        app.logger.debug(f"APPID长度: {len(params['appid']) if params['appid'] else 0}, SECRET已配置: {'是' if params['secret'] else '否'}")
        
        # 请求微信API
        response = requests.get(wx_url, params=params, timeout=10)
        app.logger.debug(f"微信服务器响应状态码: {response.status_code}")
        app.logger.debug(f"微信服务器响应内容: {response.text}")
        
        if response.status_code != 200:
            app.logger.error(f"微信服务器HTTP错误: {response.status_code}")
            return jsonify({'code': 500, 'msg': f'微信服务器响应错误: {response.status_code}'}), 500
            
        # 解析响应
        try:
            res = response.json()
        except ValueError:
            app.logger.error(f"解析微信响应JSON失败: {response.text}")
            return jsonify({'code': 500, 'msg': '无法解析微信服务器响应'}), 500
            
        # 输出详细的微信响应日志（生产环境应移除敏感信息）
        if 'errcode' in res and res['errcode'] != 0:
            error_msg = f"微信登录失败: code {res.get('errcode')}, msg: {res.get('errmsg')}"
            app.logger.warning(error_msg)
            
            # 特定错误码的处理
            if res.get('errcode') == 40029:
                app.logger.warning(f"无效的code: {code[:10]}..., 可能已过期或被使用过")
                return jsonify({
                    'code': 401, 
                    'msg': '登录失败: 微信授权码无效，请重新进入小程序获取', 
                    'detail': '微信code已过期或已被使用，需要重新获取',
                    'action': 'relogin',
                    'wx_error': res
                }), 401
            elif res.get('errcode') == 40163:
                return jsonify({'code': 401, 'msg': '登录失败: code已被使用，请重新获取', 'wx_error': res}), 401
            elif res.get('errcode') == 41008:
                return jsonify({'code': 401, 'msg': '登录失败: 缺少code参数', 'wx_error': res}), 401
            elif res.get('errcode') == -1:
                return jsonify({'code': 503, 'msg': '登录失败: 微信服务器繁忙，请稍后再试', 'wx_error': res}), 503
            else:
                return jsonify({'code': 401, 'msg': f"登录失败: {res.get('errmsg', '未知错误')}", 'wx_error': res}), 401
            
        if 'openid' not in res:
            app.logger.error(f"微信返回数据中没有openid: {res}")
            return jsonify({'code': 401, 'msg': '登录失败，微信未返回用户标识', 'wx_error': res}), 401

        # 记录成功的响应
        app.logger.info(f"微信登录成功，获取到openid: {res['openid'][:5]}...")
        
        # 更新用户信息 - 使用事务保证数据一致性
        try:
            openid = res['openid']
            session_key = res.get('session_key')
            unionid = res.get('unionid')
            
            # 创建或更新用户
            user = User.query.filter_by(openid=openid).first()
            if not user:
                app.logger.info(f"创建新用户, openid: {openid[:5]}...")
                user = User(
                    openid=openid,
                    session_key=session_key,
                    unionid=unionid
                )
                db.session.add(user)
            else:
                app.logger.info(f"更新现有用户, ID: {user.id}")
                user.session_key = session_key
                if unionid and not user.unionid:
                    user.unionid = unionid
                user.updated_at = datetime.now()
                
            db.session.commit()
            
            # 生成JWT令牌
            expires = timedelta(days=30)  # 令牌有效期30天
            access_token = create_access_token(
                identity=str(user.id),
                expires_delta=expires,
                additional_claims={'role': user.role}
            )
            
            return jsonify({
                'code': 0,
                'token': access_token,
                'user_id': user.id,
                'expires_in': expires.total_seconds()
            })
            
        except Exception as db_error:
            db.session.rollback()
            app.logger.error(f"数据库操作失败: {str(db_error)}")
            return jsonify({'code': 500, 'msg': '用户数据处理失败'}), 500
            
    except requests.RequestException as e:
        app.logger.error(f"请求微信API网络错误: {str(e)}")
        return jsonify({'code': 500, 'msg': f'网络请求失败: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"登录过程发生未预期错误: {str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'}), 500

# 用户信息接口 - 获取当前登录用户的信息
@user_bp.route('/user/info', methods=['GET'])
@jwt_required()
def get_user_info():
    try:
        # 获取当前登录用户ID
        user_id = get_jwt_identity()
        
        # 查询用户信息
        user = User.query.get(user_id)
        if not user:
            return jsonify({'code': 404, 'msg': '用户不存在'}), 404
        
        # 查询用户的自选股数量
        stocks_count = UserStock.query.filter_by(user_id=user_id).count()
        
        # 构建并返回用户数据（不包括敏感信息）
        return jsonify({
            'code': 0,
            'data': {
                'user_id': user.id,
                'nickname': user.nickname,
                'avatar_url': user.avatar_url,
                'role': user.role,
                'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'stocks_count': stocks_count,
            }
        })
    except Exception as e:
        app.logger.error(f"获取用户信息失败: {str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'}), 500
