# -*- coding: utf-8 -*-

import base64
import json

from odoo import http
from odoo.http import request


def _json_for_script(value):
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


class DtscOverviewDashboardController(http.Controller):
    @http.route('/dtsc/overview/open_action', type='http', auth='user')
    def open_action(self, token=None, payload=None, view_type=None, cids=None, debug=None, **kwargs):
        action = self._decode_action_payload(payload)
        if not action and not token:
            return request.redirect('/web#action=menu')

        action_json = _json_for_script(action)
        token_json = _json_for_script(token or "")
        view_type_json = _json_for_script(view_type or "")
        cids_json = _json_for_script(cids or "")
        debug_json = _json_for_script(debug or "")
        html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Opening...</title>
</head>
<body>
  <script>
    (function () {{
      var action = {action_json};
      var token = {token_json};
      var viewType = {view_type_json};
      var cids = {cids_json};
      var debug = {debug_json};
      if (!action && token) {{
        try {{
          var storageKey = "dtsc_overview_action_" + token;
          action = JSON.parse(window.localStorage.getItem(storageKey) || "null");
          window.localStorage.removeItem(storageKey);
        }} catch (error) {{
          action = null;
        }}
      }}
      if (!action || !action.res_model) {{
        window.location.replace("/web#action=menu");
        return;
      }}

      var targetViewType = viewType || (action.res_id ? "form" : "list");
      var hash = new URLSearchParams();
      if (cids) {{
        hash.set("cids", cids);
      }}
      hash.set("model", action.res_model);
      hash.set("view_type", targetViewType);
      if (action.res_id) {{
        hash.set("id", action.res_id);
      }}

      var search = new URLSearchParams();
      if (debug) {{
        search.set("debug", debug);
      }}
      var webUrl = "/web" + (search.toString() ? "?" + search.toString() : "") + "#" + hash.toString();
      try {{
        window.sessionStorage.setItem("current_action", JSON.stringify(action));
      }} catch (error) {{
        // Odoo uses sessionStorage to restore dynamic act_window actions.
      }}
      window.location.replace(webUrl);
    }})();
  </script>
</body>
</html>"""
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store'),
        ])

    def _decode_action_payload(self, payload):
        if not payload:
            return None
        try:
            normalized = payload.replace('-', '+').replace('_', '/')
            normalized += '=' * (-len(normalized) % 4)
            action = json.loads(base64.b64decode(normalized).decode('utf-8'))
        except Exception:
            return None

        if not isinstance(action, dict):
            return None
        if action.get('type') != 'ir.actions.act_window':
            return None
        if not isinstance(action.get('res_model'), str) or not action['res_model']:
            return None
        return action
