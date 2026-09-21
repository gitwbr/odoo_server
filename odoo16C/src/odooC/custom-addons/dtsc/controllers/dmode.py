from urllib.parse import parse_qs

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home as WebHome
from odoo.addons.web.controllers.main import WebClient as WebWebClient


def _is_dmode_on(environ) -> bool:
    """只有 dmode=777 才視為開啟，其他一律關閉。"""
    raw_qs = environ.get("QUERY_STRING", "")
    qs = parse_qs(raw_qs, keep_blank_values=True)
    vals = qs.get("dmode")
    return bool(vals and vals[0] == "777")


class Home(WebHome):
    """覆寫 /web：只看 dmode；忽略任何 debug=..."""

    @http.route("/web", type="http", auth="user")
    def web_client(self, s_action=None, **kw):
        # 永遠忽略外部帶進來的 debug
        kw.pop("debug", None)

        if _is_dmode_on(request.httprequest.environ):
            # 開啟：讓核心走 assets/debug 模式
            request.session.debug = "assets"
            kw["debug"] = "1"  # 有些流程仍讀 kw['debug']
        else:
            # 關閉：設為空字串而非 None，避免 "assets" in None 的 TypeError
            request.session.debug = ""   # << 這裡從 None 改成 ""

        return super().web_client(s_action=s_action, **kw)


class WebClient(WebWebClient):
    """覆寫 /web/bundle：只看 dmode；忽略任何 debug 與 session.debug。"""

    @http.route("/web/bundle/<string:bundle_name>", auth="public", methods=["GET"])
    def bundle(self, bundle_name, **bundle_params):
        # 語言處理維持原樣
        if "lang" in bundle_params:
            request.update_context(lang=bundle_params["lang"])

        # 僅用 dmode 決定是否回傳 debug 資產
        debug = "1" if _is_dmode_on(request.httprequest.environ) else None

        files = request.env["ir.qweb"]._get_asset_nodes(
            bundle_name, debug=debug, js=True, css=True
        )
        data = [
            {
                "type": tag,
                "src": attrs.get("src") or attrs.get("data-src") or attrs.get("href"),
                "content": content,
            }
            for tag, attrs, content in files
        ]
        return request.make_json_response(data)