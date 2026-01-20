/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";

// 自定义文档URL - 请将下面的链接替换为您的实际链接
const CUSTOM_DOCUMENTATION_URL = "https://euhon.com/pdf/action.pdf"; // 请替换为您的链接

// 获取用户菜单注册表
const userMenuRegistry = registry.category("user_menuitems");

// 等待所有模块加载完成后再执行
// 使用setTimeout确保在Odoo标准模块的user_menu_items.js注册完成后再执行
setTimeout(() => {
    // 只替换documentation项，不影响其他菜单项
    if (userMenuRegistry.contains("documentation")) {
        userMenuRegistry.remove("documentation");
    }
    
    // 添加自定义的documentation菜单项
    userMenuRegistry.add("documentation", (env) => {
        return {
            type: "item",
            id: "documentation",
            description: env._t("Documentation"),
            href: CUSTOM_DOCUMENTATION_URL,
            callback: () => {
                browser.open(CUSTOM_DOCUMENTATION_URL, "_blank");
            },
            sequence: 10,
        };
    });
}, 500); // 延迟500ms确保原始菜单项已注册

