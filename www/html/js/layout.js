// 创建公共布局
function createLayout() {
    // 创建侧边栏
    const sidebar = `
        <div class="sidebar">
            <div class="logo">
                Odoo SaaS
            </div>
            <ul class="nav-menu">
                <li>
                    <a href="/dashboard/index.html" class="nav-item" id="nav-dashboard">
                        <i class="material-icons">dashboard</i>
                        控制台
                    </a>
                </li>
                <li>
                    <a href="/dashboard/instance.html" class="nav-item" id="nav-instance">
                        <i class="material-icons">dns</i>
                        實例管理
                    </a>
                </li>
                <li>
                    <a href="#" class="nav-item" id="nav-settings">
                        <i class="material-icons">settings</i>
                        系統設置
                    </a>
                </li>
            </ul>
        </div>
    `;

    // 获取页面主容器
    const dashboard = document.querySelector('.dashboard');
    
    // 插入侧边栏
    dashboard.insertAdjacentHTML('afterbegin', sidebar);
    
    // 根据当前页面设置活动菜单项
    const currentPath = window.location.pathname;
    const navItems = {
        '/dashboard/index.html': 'nav-dashboard',
        '/dashboard/instance.html': 'nav-instance'
    };
    
    const activeNavId = navItems[currentPath];
    if (activeNavId) {
        document.getElementById(activeNavId).classList.add('active');
    }
}

// 页面加载时初始化布局
document.addEventListener('DOMContentLoaded', createLayout); 