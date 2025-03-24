from flask import Blueprint, request, jsonify, session
from utils.database import get_db_connection
from datetime import datetime
import logging
import json

message_bp = Blueprint('message', __name__)
logger = logging.getLogger(__name__)

@message_bp.route('/list', methods=['GET'])
def get_messages():
    try:
        logger.debug('開始獲取消息列表')
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({
                'messages': [],
                'error': '未登錄'
            }), 401

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT m.*, 
                           s.username as sender_name,
                           r.username as receiver_name
                    FROM internal_messages m
                    JOIN users s ON m.sender_id = s.id
                    JOIN users r ON m.receiver_id = r.id
                    WHERE m.sender_id = %s OR m.receiver_id = %s
                    ORDER BY m.created_at DESC
                """, (user_id, user_id))
                messages = cur.fetchall()
                logger.debug(f'查詢到 {len(messages) if messages else 0} 條消息')
                
                return jsonify({
                    'messages': [{
                        'id': msg[0],
                        'subject': msg[1],
                        'content': msg[2],
                        'sender_id': msg[3],
                        'receiver_id': msg[4],
                        'status': msg[5],
                        'priority': msg[6],
                        'read_at': msg[7],
                        'processed_at': msg[8],
                        'created_at': msg[9],
                        'sender_name': msg[11],
                        'receiver_name': msg[12]
                    } for msg in messages] if messages else []
                })
    except Exception as e:
        logger.error(f'獲取消息列表失敗: {str(e)}')
        logger.exception(e)
        return jsonify({
            'messages': [],
            'error': str(e)
        }), 500

@message_bp.route('/create', methods=['POST'])
def create_message():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登錄'}), 401

        data = request.get_json()
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO internal_messages 
                    (subject, content, sender_id, receiver_id, priority)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    data['subject'],
                    data['content'],
                    user_id,
                    data['receiver_id'],
                    data['priority']
                ))
                message_id = cur.fetchone()[0]
                conn.commit()
                
                return jsonify({'id': message_id}), 201
    except Exception as e:
        logger.error(f'創建消息失敗: {str(e)}')
        logger.exception(e)
        return jsonify({'error': str(e)}), 500

@message_bp.route('/<int:message_id>/read', methods=['POST'])
def mark_as_read(message_id):
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登錄'}), 401

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 先获取消息信息
                cur.execute("SELECT subject FROM internal_messages WHERE id = %s", (message_id,))
                message = cur.fetchone()
                if not message:
                    return jsonify({'error': '消息不存在'}), 404
                    
                cur.execute("""
                    UPDATE internal_messages
                    SET status = 'read',
                        read_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND receiver_id = %s
                """, (message_id, user_id))
                conn.commit()
                return jsonify({'success': True})
    except Exception as e:
        logger.error(f'標記已讀失敗: {str(e)}')
        logger.exception(e)
        return jsonify({'error': str(e)}), 500

@message_bp.route('/<int:message_id>/process', methods=['POST'])
def start_processing(message_id):
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登錄'}), 401

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE internal_messages
                    SET status = 'processing'
                    WHERE id = %s AND receiver_id = %s
                """, (message_id, user_id))
                conn.commit()
                return jsonify({'success': True})
    except Exception as e:
        logger.error(f'開始處理失敗: {str(e)}')
        logger.exception(e)
        return jsonify({'error': str(e)}), 500

@message_bp.route('/<int:message_id>/done', methods=['POST'])
def mark_as_done(message_id):
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登錄'}), 401

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE internal_messages
                    SET status = 'done',
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND receiver_id = %s
                """, (message_id, user_id))
                conn.commit()
                return jsonify({'success': True})
    except Exception as e:
        logger.error(f'標記完成失敗: {str(e)}')
        logger.exception(e)
        return jsonify({'error': str(e)}), 500 