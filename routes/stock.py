from flask import Blueprint, jsonify, request, current_app as app
from flask_jwt_extended import jwt_required, get_jwt_identity
import akshare as ak
import time

from models import db, UserStock
from ai_utils import extract_stocks_from_base64

# 创建蓝图
stock_bp = Blueprint('stock', __name__, url_prefix='/api')

# 股票管理接口
@stock_bp.route('/stocks/get', methods=['GET'])
@jwt_required()
def get_stocks():
    """获取当前用户的所有自选股票"""
    try:
        user_id = get_jwt_identity()
        
        # 获取自选股列表
        stocks = UserStock.query.filter_by(user_id=user_id).all()
        
        return jsonify({
            'code': 0,
            'data': [{
                'id': s.id,
                'code': s.code,
                'name': s.name,
                'added_at': s.added_at.strftime('%Y-%m-%d %H:%M:%S')
            } for s in stocks]
        })
    except Exception as e:
        app.logger.error(f"获取股票失败: {str(e)}")
        return jsonify({'code': 500, 'msg': f'服务器内部错误: {str(e)}'}), 500

@stock_bp.route('/stocks/add', methods=['POST'])
@jwt_required()
def add_stocks():
    """批量添加自选股票"""
    try:
        user_id = get_jwt_identity()
        data = request.json
        
        if not data or 'stocks' not in data or not isinstance(data['stocks'], list):
            return jsonify({'code': 400, 'msg': '请求格式错误，需要提供stocks列表'}), 400
            
        if len(data['stocks']) > 20:
            return jsonify({'code': 400, 'msg': '单次最多添加20只股票'}), 400
        
        # 当前用户已有的股票代码集合
        existing_codes = {s.code for s in UserStock.query.filter_by(user_id=user_id).all()}
        
        added_stocks = []
        error_stocks = []
        
        for stock in data['stocks']:
            # 跳过已添加的股票
            if stock['code'] in existing_codes:
                error_stocks.append({
                    'code': stock['code'],
                    'reason': '已在自选列表中'
                })
                continue
                
            # 验证股票代码有效性并获取名称
            try:
                stock_name = stock.get('name', '')  # 优先使用传入的名称
                stock_code = stock['code']
                
                # 如果没有传入名称，尝试从akshare获取
                if not stock_name:
                    app.logger.debug(f"尝试获取股票 {stock_code} 的信息")
                    stock_info = ak.stock_individual_info_em(symbol=stock_code)
                    
                    # 调试输出数据结构
                    app.logger.debug(f"股票信息类型: {type(stock_info)}")
                    app.logger.debug(f"股票信息是否为空: {stock_info.empty}")
                    
                    if not stock_info.empty:
                        # 输出列名以便调试
                        app.logger.debug(f"股票信息列名: {stock_info.columns.tolist()}")
                        
                        # 安全地获取股票名称
                        if '股票简称' in stock_info.columns:
                            stock_name = stock_info.iloc[0]['股票简称']
                        elif '证券简称' in stock_info.columns:
                            stock_name = stock_info.iloc[0]['证券简称']
                        elif '名称' in stock_info.columns:
                            stock_name = stock_info.iloc[0]['名称']
                        else:
                            # 如果找不到名称，使用第一列的值
                            first_col = stock_info.columns[0]
                            app.logger.warning(f"未找到股票名称列，使用第一列 '{first_col}' 的值")
                            stock_name = str(stock_info.iloc[0][first_col])
                    else:
                        error_stocks.append({
                            'code': stock_code,
                            'reason': '无效的股票代码'
                        })
                        continue
                
                # 如果仍然没有名称，使用代码作为名称
                if not stock_name:
                    app.logger.warning(f"无法获取股票 {stock_code} 的名称，使用代码作为名称")
                    stock_name = f"股票{stock_code}"

                # 添加自选股
                app.logger.info(f"添加股票: 代码={stock_code}, 名称={stock_name}")
                new_stock = UserStock(
                    user_id=user_id,
                    code=stock_code,
                    name=stock_name
                )
                db.session.add(new_stock)
                added_stocks.append({
                    'code': stock_code,
                    'name': stock_name
                })
                existing_codes.add(stock_code)  # 更新集合，防止本次请求中重复添加
                
            except Exception as e:
                app.logger.error(f"添加股票 {stock['code']} 时发生错误: {str(e)}")
                app.logger.exception(e)  # 记录完整堆栈
                error_stocks.append({
                    'code': stock['code'],
                    'reason': f'处理异常: {str(e)}'
                })
        
        db.session.commit()
        
        return jsonify({
            'code': 0,
            'data': {
                'added': added_stocks,
                'errors': error_stocks,
                'total_added': len(added_stocks)
            }
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"批量添加股票失败: {str(e)}")
        app.logger.exception(e)
        return jsonify({'code': 500, 'msg': f'服务器内部错误: {str(e)}'}), 500

@stock_bp.route('/stocks/remove', methods=['POST'])
@jwt_required()
def remove_stocks():
    """批量删除自选股票"""
    try:
        user_id = get_jwt_identity()
        data = request.json
        
        if not data or 'stock_ids' not in data or not isinstance(data['stock_ids'], list):
            return jsonify({'code': 400, 'msg': '请求格式错误，需要提供stock_ids列表'}), 400
        
        if len(data['stock_ids']) > 50:
            return jsonify({'code': 400, 'msg': '单次最多删除50只股票'}), 400
            
        # 查找所有需要删除的记录，确保它们属于当前用户
        to_delete = UserStock.query.filter(
            UserStock.id.in_(data['stock_ids']),
            UserStock.user_id == user_id
        ).all()
        
        # 记录成功删除的ID
        deleted_ids = []
        
        for stock in to_delete:
            deleted_ids.append(stock.id)
            db.session.delete(stock)
            
        db.session.commit()
        
        # 返回已删除的ID和数量
        return jsonify({
            'code': 0,
            'data': {
                'deleted_ids': deleted_ids,
                'total_deleted': len(deleted_ids)
            }
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"批量删除股票失败: {str(e)}")
        return jsonify({'code': 500, 'msg': f'服务器内部错误: {str(e)}'}), 500

# 图片添加股票接口
@stock_bp.route('/stocks/add_from_image', methods=['POST'])
@jwt_required()
def add_stocks_from_image():
    """通过图片OCR批量添加自选股票"""
    try:
        user_id = get_jwt_identity()
        app.logger.debug(f"处理用户 {user_id} 的图片识别请求")
        
        data = request.json
        if not data:
            app.logger.error("请求体为空或不是JSON格式")
            return jsonify({'code': 400, 'msg': '请求格式错误，需要JSON数据'}), 400
            
        if 'image' not in data or not data.get('image'):
            app.logger.error("请求中缺少image字段或为空")
            return jsonify({'code': 400, 'msg': '缺少必要的图片数据'}), 400
            
        # 获取base64图片数据
        image_base64 = data.get('image')
        app.logger.info(f"接收到图片数据，长度: {len(image_base64)}, 前20字符: {image_base64[:20]}...")
        
        # 检查base64格式
        if "base64," in image_base64:
            app.logger.debug(f"检测到Data URL格式，将提取纯base64部分")
            prefix = image_base64.split("base64,")[0]
            app.logger.debug(f"图片前缀: {prefix}")
        
        try:
            # 使用AI工具提取股票信息
            app.logger.debug("开始调用OCR服务提取股票信息...")
            stock_items = extract_stocks_from_base64(image_base64)
            app.logger.debug(f"OCR服务返回原始结果: {stock_items}")
            
            if not stock_items:
                app.logger.warning("OCR服务未能识别出任何股票信息")
                return jsonify({'code': 400, 'msg': '未从图片中识别出任何股票信息'}), 400
                
            app.logger.info(f"从图片中识别出 {len(stock_items)} 只股票: {stock_items}")
            
            # 解析识别结果，格式为："股票名称 股票代码"
            stocks_to_add = []
            rejected_items = []
            
            app.logger.debug("开始解析股票信息...")
            for i, item in enumerate(stock_items):
                app.logger.debug(f"处理第{i+1}项: '{item}'")
                parts = item.strip().split()
                app.logger.debug(f"拆分后: {parts}")
                
                if len(parts) >= 2:  # 确保至少有名称和代码两部分
                    # 取最后一项作为代码，其余的合并为名称
                    code = parts[-1]
                    name = ' '.join(parts[:-1])
                    app.logger.debug(f"提取到名称: '{name}', 代码: '{code}'")
                    
                    # 验证代码格式（6位数字）
                    if code.isdigit() and len(code) == 6:
                        stocks_to_add.append({
                            'code': code,
                            'name': name
                        })
                        app.logger.debug(f"有效股票: {name} {code}")
                    else:
                        app.logger.warning(f"无效股票代码格式: {code}")
                        rejected_items.append({
                            'item': item,
                            'reason': '无效股票代码格式'
                        })
                else:
                    app.logger.warning(f"项目格式不正确: {item}")
                    rejected_items.append({
                        'item': item,
                        'reason': '格式不符合"名称 代码"'
                    })
            
            if not stocks_to_add:
                app.logger.warning(f"未能解析出有效股票信息，被拒绝的项: {rejected_items}")
                return jsonify({
                    'code': 400, 
                    'msg': '未能正确解析出股票信息，请确保图片清晰',
                    'detail': rejected_items
                }), 400
                
            # 构造批量添加请求，调用已有的add_stocks逻辑
            add_request = {'stocks': stocks_to_add}
            app.logger.info(f"准备添加 {len(stocks_to_add)} 只股票: {stocks_to_add}")
            
            # 将股票添加请求暂存到session中
            session_key = f"pending_stocks_{user_id}"
            app.config[session_key] = add_request
            app.logger.debug(f"已将股票数据存入会话: {session_key}")
            
            # 返回预览信息，让用户确认
            return jsonify({
                'code': 0,
                'msg': f'成功识别出{len(stocks_to_add)}只股票',
                'data': {
                    'stocks': stocks_to_add,
                    'total': len(stocks_to_add),
                    'rejected': rejected_items if rejected_items else None
                }
            })
            
        except Exception as ocr_error:
            app.logger.error(f"图片识别处理失败: {str(ocr_error)}")
            app.logger.exception(ocr_error)  # 记录完整异常堆栈
            return jsonify({'code': 500, 'msg': f'图片处理失败: {str(ocr_error)}'}), 500
            
    except Exception as e:
        app.logger.error(f"添加股票图片处理失败: {str(e)}")
        app.logger.exception(e)  # 记录完整异常堆栈
        return jsonify({'code': 500, 'msg': f'服务器内部错误: {str(e)}'}), 500

@stock_bp.route('/stocks/confirm_from_image', methods=['POST'])
@jwt_required()
def confirm_stocks_from_image():
    """确认添加从图片中识别的股票"""
    try:
        user_id = get_jwt_identity()
        app.logger.debug(f"用户 {user_id} 确认添加图片识别的股票")
        
        # 从session获取暂存的股票数据
        session_key = f"pending_stocks_{user_id}"
        app.logger.debug(f"查找会话键: {session_key}")
        
        if session_key not in app.config:
            app.logger.warning(f"未找到会话数据: {session_key}")
            return jsonify({'code': 400, 'msg': '没有待确认的股票数据，请重新上传图片'}), 400
            
        # 获取暂存的股票列表并清除session
        add_request = app.config.pop(session_key)
        app.logger.info(f"从会话中取出待添加股票: {add_request}")
        
        # 使用已有的批量添加接口处理
        app.logger.debug("修改请求体，准备调用添加股票接口")
        request._cached_json = (add_request, request._cached_json[1])  # 修改请求的JSON数据
        app.logger.debug("调用 add_stocks() 完成添加")
        return add_stocks()
        
    except Exception as e:
        app.logger.error(f"确认添加图片股票失败: {str(e)}")
        app.logger.exception(e)  # 记录完整异常堆栈
        return jsonify({'code': 500, 'msg': f'服务器内部错误: {str(e)}'}), 500


# 股票搜索接口
@stock_bp.route('/stocks/search', methods=['GET'])
@jwt_required()
def search_stocks():
    """搜索股票，支持代码或名称模糊匹配"""
    try:
        # 获取查询参数
        keyword = request.args.get('keyword', '')
        limit = min(int(request.args.get('limit', 10)), 30)  # 默认10条，最多30条
        
        if not keyword or len(keyword) < 2:
            return jsonify({
                'code': 400,
                'msg': '搜索关键词不能少于2个字符'
            }), 400
            
        app.logger.info(f"搜索股票，关键词: {keyword}, 限制: {limit}")
        
        try:
            # 使用akshare获取A股列表
            app.logger.debug("开始从akshare获取股票数据...")
            start_time = time.time()
            
            # 尝试使用ak接口获取A股列表
            try:
                # 优先尝试使用股票列表接口
                stock_list = ak.stock_zh_a_spot_em()
                app.logger.debug(f"获取A股列表成功，数据量: {len(stock_list)}")
                
                # 检查返回的列
                columns = stock_list.columns.tolist()
                app.logger.debug(f"股票列表字段: {columns}")
                
                # 确定名称和代码的列名
                name_col = next((col for col in ['名称', '股票名称', '证券名称'] if col in columns), '名称')
                code_col = next((col for col in ['代码', '股票代码', '证券代码'] if col in columns), '代码')
                
                app.logger.debug(f"使用列: 名称={name_col}, 代码={code_col}")
                
            except Exception as ak_error:
                app.logger.error(f"使用ak.stock_zh_a_spot_em失败: {str(ak_error)}")
                app.logger.warning("尝试备用接口...")
                
                # 备用接口
                try:
                    stock_list = ak.stock_info_a_code_name()
                    app.logger.debug(f"使用备用接口成功，数据量: {len(stock_list)}")
                    
                    # 检查返回的列
                    columns = stock_list.columns.tolist()
                    app.logger.debug(f"备用接口股票列表字段: {columns}")
                    
                    # 备用接口的列名可能不同
                    name_col = columns[1] if len(columns) > 1 else '股票简称'
                    code_col = columns[0] if len(columns) > 0 else '股票代码'
                    
                    app.logger.debug(f"使用备用列: 名称={name_col}, 代码={code_col}")
                    
                except Exception as backup_error:
                    app.logger.error(f"备用接口也失败: {str(backup_error)}")
                    return jsonify({
                        'code': 500,
                        'msg': '获取股票列表失败，请稍后再试'
                    }), 500
            
            end_time = time.time()
            app.logger.debug(f"获取股票列表耗时: {end_time - start_time:.2f}秒")
            
            # 确保列名存在
            if name_col not in stock_list.columns or code_col not in stock_list.columns:
                app.logger.error(f"数据列错误: 期望{name_col}和{code_col}，实际有{stock_list.columns.tolist()}")
                return jsonify({
                    'code': 500,
                    'msg': '股票数据格式异常，无法搜索'
                }), 500
            
            # 进行模糊匹配
            app.logger.debug("开始过滤匹配的股票...")
            # 转换为大小写不敏感
            keyword_lower = keyword.lower()
            
            # 筛选匹配项
            matched_stocks = []
            
            # 确保字符串类型比较
            stock_list[name_col] = stock_list[name_col].astype(str)
            stock_list[code_col] = stock_list[code_col].astype(str)
            
            for _, row in stock_list.iterrows():
                name = row[name_col]
                code = row[code_col]
                
                # 移除代码中的可能前缀
                if '.' in code:
                    code = code.split('.')[0]
                
                # 如果关键词在名称或代码中出现
                if (keyword_lower in name.lower() or 
                    keyword_lower in code.lower() or 
                    code.startswith(keyword)):
                    
                    matched_stocks.append({
                        'code': code,
                        'name': name
                    })
                    
                    # 达到限制数量后停止
                    if len(matched_stocks) >= limit:
                        break
            
            app.logger.info(f"搜索结果: 找到{matched_stocks}个匹配项")

            
            return jsonify({
                'code': 0,
                'data': {
                    'stocks': matched_stocks,
                    'total': len(matched_stocks),
                    'keyword': keyword
                }
            })
            
        except Exception as search_error:
            app.logger.error(f"搜索处理异常: {str(search_error)}")
            app.logger.exception(search_error)
            return jsonify({
                'code': 500,
                'msg': f'搜索处理失败: {str(search_error)}'
            }), 500
            
    except Exception as e:
        app.logger.error(f"股票搜索接口异常: {str(e)}")
        app.logger.exception(e)
        return jsonify({
            'code': 500,
            'msg': f'服务器内部错误: {str(e)}'
        }), 500
