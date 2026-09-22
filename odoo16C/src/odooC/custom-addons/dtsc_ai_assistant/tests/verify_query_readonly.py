"""Manual read-only query verification, not an Odoo integration test.

Use the same config as the test service and a real non-superuser UID.
PGOPTIONS protects registry connections too. Does not call answer_question or create logs.
Queries are supplied as JSON CLI arguments, never inferred by this verification script.
"""
import argparse
import json
import os
import time

parser = argparse.ArgumentParser()
parser.add_argument('--config', required=True)
parser.add_argument('--database', required=True)
parser.add_argument('--uid', type=int, required=True)
parser.add_argument('--query', action='append', required=True)
args = parser.parse_args()
if args.uid == 1:
    parser.error('Use an actual user, not the Odoo superuser.')
if os.environ.get('PGOPTIONS') != '-c default_transaction_read_only=on':
    parser.error('Set PGOPTIONS=-c default_transaction_read_only=on before starting.')

import odoo
from odoo import api
odoo.tools.config.parse_config(['-c', args.config, '--no-http'])
registry = odoo.registry(args.database)
with registry.cursor() as cr:
    cr.execute('SHOW transaction_read_only')
    assert cr.fetchone()[0] == 'on', 'Database connection must be read-only'
    env = api.Environment(cr, args.uid, {'lang': 'zh_TW', 'tz': 'Asia/Taipei'})
    query = env['dtsc.ai.universal.query']
    for raw in args.query:
        request = json.loads(raw)
        started = time.monotonic()
        response = query.execute(request, actor={'actor_type': 'internal'})
        print('VERIFICATION ' + json.dumps({
            'user_id': args.uid, 'request': request, 'elapsed_ms': round((time.monotonic()-started)*1000),
            'result': response,
        }, ensure_ascii=False, default=str))
    cr.rollback()
