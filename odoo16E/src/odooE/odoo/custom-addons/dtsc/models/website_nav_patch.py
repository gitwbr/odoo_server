# -*- coding: utf-8 -*-

import logging

from lxml import etree

from odoo import api, models


_logger = logging.getLogger(__name__)


class DtscWebsiteNavPatch(models.AbstractModel):
    _name = 'dtsc.website.nav.patch'
    _description = 'DTSC Website Navigation Patch'

    PATCH_VERSION = '2026-07-09-v2'
    PATCH_VERSION_KEY = 'dtsc.official_site_nav_patch_version'
    AI_ENTRY_URL = '/ai-entry'
    AI_ENTRY_TEXT = 'AI 印前檢測-會員專屬'
    CHECKOUT_ENTRY_URL = '/my/checkout-entry'
    CHECKOUT_ENTRY_TEXT = '我的大圖訂單'

    @api.model
    def apply_official_site_nav_changes(self):
        self = self.sudo()
        parameters = self.env['ir.config_parameter'].sudo()
        if parameters.get_param(self.PATCH_VERSION_KEY) == self.PATCH_VERSION:
            return True

        self._patch_logo_links()
        self._patch_shop_menu_name()
        self._hide_ai_menu_from_dropdown()
        self._patch_header_cta_buttons()
        parameters.set_param(self.PATCH_VERSION_KEY, self.PATCH_VERSION)
        return True

    def _patch_logo_links(self):
        View = self.env['ir.ui.view']
        views = View.search([
            ('key', 'in', [
                'website.option_header_brand_logo',
                'website.option_header_brand_name',
            ]),
        ])
        for view in views:
            new_arch = self._replace_logo_href(view.arch_db or '')
            if new_arch != (view.arch_db or ''):
                view.write({'arch_db': new_arch})
                _logger.info('Updated website logo link on view %s', view.key)

    def _patch_shop_menu_name(self):
        Menu = self.env['website.menu']
        menus = Menu.search([
            ('url', 'in', ['/shop', '/shop/']),
        ])
        if not menus:
            return

        for menu in menus:
            menu.with_context(lang=False).write({'name': '線上商城'})
            for lang in self.env['res.lang'].search([('active', '=', True)]):
                menu.with_context(lang=lang.code).write({'name': '線上商城'})

    def _hide_ai_menu_from_dropdown(self):
        Menu = self.env['website.menu']
        menus = Menu.search([
            ('url', '=', self.AI_ENTRY_URL),
            ('name', 'ilike', 'AI 印前檢測'),
        ])
        menus.filtered('parent_id').write({'parent_id': False})

    def _patch_header_cta_buttons(self):
        View = self.env['ir.ui.view']
        views = View.search([
            ('key', '=', 'website.header_call_to_action'),
            ('arch_db', 'ilike', self.CHECKOUT_ENTRY_URL),
        ])
        for view in views:
            arch = view.arch_db or ''
            new_arch = self._patch_header_cta_arch(arch)
            if new_arch != arch:
                view.write({'arch_db': new_arch})
                _logger.info('Updated website header CTA on view %s', view.key)

    def _replace_logo_href(self, arch):
        def patch(root):
            changed = False
            for node in root.xpath(".//a[@href='/']"):
                classes = '%s %s' % (
                    node.get('class') or '',
                    node.get('t-attf-class') or '',
                )
                if 'navbar-brand' in classes:
                    node.set('href', '/index')
                    changed = True
            return changed

        patched = self._patch_xml_fragment(arch, patch)
        if patched != arch:
            return patched

        return arch.replace(
            '<a href="/" t-attf-class="navbar-brand logo #{_link_class}">',
            '<a href="/index" t-attf-class="navbar-brand logo #{_link_class}">',
        ).replace(
            '<a href="/" t-attf-class="navbar-brand #{_link_class}">',
            '<a href="/index" t-attf-class="navbar-brand #{_link_class}">',
        )

    def _patch_header_cta_arch(self, arch):
        def patch(root):
            checkout_links = root.xpath(".//a[@href='%s']" % self.CHECKOUT_ENTRY_URL)
            if not checkout_links:
                return False

            changed = False
            checkout_link = checkout_links[0]
            changed |= self._mark_header_cta(checkout_link)
            changed |= self._ensure_class(checkout_link, 'o_my_checkout_entry_btn')
            changed |= self._remove_class(checkout_link, 'o_dtsc_checkout_entry_btn')

            ai_links = root.xpath(".//a[@href='%s']" % self.AI_ENTRY_URL)
            if ai_links:
                for ai_link in ai_links:
                    changed |= self._remove_class(ai_link, 'o_dtsc_ai_entry_btn')
                return changed

            parent = checkout_link.getparent()
            ai_link = etree.Element('a', href=self.AI_ENTRY_URL)
            ai_link.set('class', checkout_link.get('class') or '_cta btn btn-primary')
            self._remove_class(ai_link, 'o_my_checkout_entry_btn')
            ai_link.text = self.AI_ENTRY_TEXT
            ai_link.tail = checkout_link.tail
            parent.insert(parent.index(checkout_link), ai_link)
            return True

        patched = self._patch_xml_fragment(arch, patch)
        if patched != arch:
            return patched

        checkout_html = '<a href="%s" class="_cta btn btn-primary">%s</a>' % (
            self.CHECKOUT_ENTRY_URL,
            self.CHECKOUT_ENTRY_TEXT,
        )
        ai_html = '<a href="%s" class="_cta btn btn-primary">%s</a>' % (
            self.AI_ENTRY_URL,
            self.AI_ENTRY_TEXT,
        )
        if checkout_html in arch:
            return arch.replace(checkout_html, '%s\n            %s' % (ai_html, checkout_html), 1)
        return arch

    def _mark_header_cta(self, checkout_link):
        changed = False
        parent = checkout_link.getparent()
        if parent is not None:
            changed |= self._ensure_class(parent, 'o_my_checkout_entry_group')
            changed |= self._remove_class(parent, 'o_dtsc_header_cta_group')
            section = parent.getparent()
            if section is not None:
                changed |= self._remove_class(section, 'o_dtsc_header_cta_section')
                wrapper = section.getparent()
                if wrapper is not None:
                    changed |= self._remove_class(wrapper, 'o_dtsc_header_cta')
        return changed

    def _ensure_class(self, node, class_name):
        classes = (node.get('class') or '').split()
        if class_name in classes:
            return False
        classes.append(class_name)
        node.set('class', ' '.join(classes))
        return True

    def _remove_class(self, node, class_name):
        classes = (node.get('class') or '').split()
        if class_name not in classes:
            return False
        classes.remove(class_name)
        node.set('class', ' '.join(classes))
        return True

    def _patch_xml_fragment(self, arch, patch):
        if not arch:
            return arch

        parser = etree.XMLParser(remove_blank_text=False)
        try:
            root = etree.fromstring(('<root>%s</root>' % arch).encode('utf-8'), parser=parser)
        except etree.XMLSyntaxError:
            return arch

        if not patch(root):
            return arch

        return ''.join(
            etree.tostring(child, encoding='unicode')
            for child in root
        )
