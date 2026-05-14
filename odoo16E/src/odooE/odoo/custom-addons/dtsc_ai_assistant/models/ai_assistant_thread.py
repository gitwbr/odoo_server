# -*- coding: utf-8 -*-

from odoo import fields, models


class AiAssistantThread(models.Model):
    _name = 'dtsc.ai.assistant.thread'
    _description = 'DTS-C AI Assistant Thread'
    _order = 'last_message_date desc, id desc'

    name = fields.Char(string='標題', readonly=True)
    user_id = fields.Many2one('res.users', string='使用者', readonly=True)
    partner_id = fields.Many2one('res.partner', string='客戶/會員', readonly=True)
    actor_type = fields.Char(string='身份類型', readonly=True)
    actor_key = fields.Char(string='身份鍵', index=True, readonly=True)
    active = fields.Boolean(default=True, readonly=True)
    last_message_date = fields.Datetime(string='最後訊息時間', readonly=True)
    message_ids = fields.One2many(
        'dtsc.ai.assistant.message',
        'thread_id',
        string='訊息',
        readonly=True,
    )

    def get_or_create_for_actor(self, actor):
        actor_key = self._actor_key(actor)
        thread = self.sudo().search([
            ('actor_key', '=', actor_key),
            ('active', '=', True),
        ], order='last_message_date desc, id desc', limit=1)
        if thread:
            return thread

        return self.sudo().create({
            'name': actor.get('display_name') or actor_key,
            'user_id': self.env.uid if actor.get('actor_type') in ('admin', 'internal') else False,
            'partner_id': actor.get('partner_id') or False,
            'actor_type': actor.get('actor_type') or '',
            'actor_key': actor_key,
            'last_message_date': fields.Datetime.now(),
        })

    def append_message(self, role, content, result=None, gateway_log_id=False):
        self.ensure_one()
        message = self.env['dtsc.ai.assistant.message'].sudo().create({
            'thread_id': self.id,
            'role': role,
            'content': content or '',
            'result_json': result or '',
            'gateway_log_id': gateway_log_id or False,
        })
        self.sudo().write({'last_message_date': fields.Datetime.now()})
        return message

    def to_gateway_messages(self, limit=12):
        self.ensure_one()
        messages = self.message_ids.sorted(lambda msg: msg.create_date)[-limit:]
        return [
            {'role': msg.role, 'content': msg.content}
            for msg in messages
            if msg.role in ('user', 'assistant') and msg.content
        ]

    def serialize_messages(self, limit=30):
        self.ensure_one()
        messages = self.message_ids.sorted(lambda msg: msg.create_date)[-limit:]
        return [message.serialize() for message in messages]

    def load_recent_for_actor(self, actor, limit=30):
        actor_key = self._actor_key(actor)
        thread = self.sudo().search([
            ('actor_key', '=', actor_key),
            ('active', '=', True),
        ], order='last_message_date desc, id desc', limit=1)
        if not thread:
            return {
                'thread_id': False,
                'messages': [],
            }
        return {
            'thread_id': thread.id,
            'messages': thread.serialize_messages(limit=limit),
        }

    @staticmethod
    def _actor_key(actor):
        actor_type = actor.get('actor_type') or 'anonymous'
        if actor_type in ('admin', 'internal'):
            return '%s:user:%s' % (actor_type, actor.get('user_id') or '')
        return '%s:partner:%s' % (actor_type, actor.get('partner_id') or '')

