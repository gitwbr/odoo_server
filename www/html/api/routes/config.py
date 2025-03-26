from flask import Blueprint, jsonify
from config import DOMAIN
import logging

logger = logging.getLogger(__name__)

config = Blueprint('config', __name__)

@config.route('/config/domain', methods=['GET'])
def get_domain():
    try:
        logger.debug('Fetching domain configuration')
        return jsonify({
            'domain': DOMAIN
        })
    except Exception as e:
        logger.error(f'Error getting domain: {str(e)}')
        return jsonify({'error': 'Failed to get domain'}), 500 
