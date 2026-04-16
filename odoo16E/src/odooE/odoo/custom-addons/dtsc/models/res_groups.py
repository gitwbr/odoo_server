# -*- coding: utf-8 -*-

from lxml import etree

from odoo import models


class GroupsView(models.Model):
    _inherit = "res.groups"

    def _update_user_groups_view(self):
        super()._update_user_groups_view()

        view = self.with_context(lang=None).env.ref(
            "base.user_groups_view", raise_if_not_found=False)
        if not (view and view._name == "ir.ui.view" and view.arch):
            return

        root = etree.fromstring(view.arch.encode())
        changed = False

        # wbr
        # 移除 "Technical" 和 "Extra Rights" 的分割線
        for section_name in ("Technical", "Extra Rights"):
            for separator in root.xpath(f".//separator[@string='{section_name}']"):
                parent = separator.getparent()
                node = separator.getnext()
                parent.remove(separator)
                changed = True

                while node is not None and node.tag != "separator":
                    next_node = node.getnext()
                    parent.remove(node)
                    node = next_node

        if changed:
            view.with_context(lang=None).write({
                "arch": etree.tostring(root, pretty_print=True, encoding="unicode")
            })
