// 创建公共布局
function createLayout() {
    // 插入布局
    insertLayout();
    
    // 根据当前页面设置活动菜单项
    const currentPath = window.location.pathname;
    const navItems = {
        '/dashboard/index.html': 'nav-dashboard',
        '/dashboard/instance.html': 'nav-instance',
        '/dashboard/profile.html': 'nav-profile'  // 添加个人资料页面
    };
    
    const activeNavId = navItems[currentPath];
    if (activeNavId) {
        document.getElementById(activeNavId).classList.add('active');
    }
}

// 插入侧边栏和顶部栏
function insertLayout() {
    // 插入顶部栏
    const header = document.createElement('div');
    header.className = 'header';
    header.innerHTML = `
        <div class="header-content">
            <div class="welcome">
                <i class="material-icons">verified_user</i>
                <span id="user-status"></span>
            </div>
            <div class="user-menu">
                <div class="user-info">
                    <div class="user-avatar"></div>
                    <span id="user-fullname">用戶名</span>
                    <i class="material-icons">arrow_drop_down</i>
                </div>
                <div class="dropdown-menu">
                    <div class="menu-item" onclick="window.location.href='/dashboard/profile.html'">
                        <i class="material-icons">person</i>
                        <span>個人資料</span>
                    </div>
                    <div class="menu-item" onclick="window.location.href='/dashboard/settings.html'">
                        <i class="material-icons">settings</i>
                        <span>系統設置</span>
                    </div>
                    <div class="divider"></div>
                    <div class="menu-item" id="logout-btn">
                        <i class="material-icons">logout</i>
                        <span>退出登錄</span>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 插入侧边栏
    const sidebar = document.createElement('div');
    sidebar.className = 'sidebar';
    sidebar.innerHTML = `
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
                <a href="/dashboard/profile.html" class="nav-item" id="nav-profile">
                    <i class="material-icons">person</i>
                    個人資料
                </a>
            </li>
            <li>
                <a href="#" class="nav-item" id="nav-settings">
                    <i class="material-icons">settings</i>
                    系統設置
                </a>
            </li>
        </ul>
    `;

    // 插入到页面
    const dashboard = document.querySelector('.dashboard');
    const mainContent = dashboard.querySelector('.main-content');
    dashboard.insertBefore(sidebar, mainContent);
    mainContent.insertBefore(header, mainContent.firstChild);

    // 插入 toast 容器
    if (!document.getElementById('toastContainer')) {
        const toastContainer = document.createElement('div');
        toastContainer.id = 'toastContainer';
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }

    // 添加用户菜单点击事件
    const userInfo = document.querySelector('.user-info');
    const dropdownMenu = document.querySelector('.dropdown-menu');
    userInfo.addEventListener('click', () => {
        dropdownMenu.classList.toggle('show');
    });

    // 点击其他地方关闭菜单
    document.addEventListener('click', (e) => {
        if (!userInfo.contains(e.target)) {
            dropdownMenu.classList.remove('show');
        }
    });

    // 添加登出按钮事件监听
    document.getElementById('logout-btn').addEventListener('click', async () => {
        // 调用 common.js 中的 logout 函数
        await logout();
    });

    // 更新用户状态显示
    function updateUserStatus(status) {
        const statusText = status === 0 ? '超级用户' : '普通用户';
        const statusEl = document.getElementById('user-status');
        if (statusEl) {
            statusEl.textContent = statusText;
        }
    }

    // 在获取用户信息后更新状态
    fetch('/api/user/info')
        .then(response => response.json())
        .then(data => {
            if (data.status !== undefined) {
                updateUserStatus(data.status);
            }
        })
        .catch(error => console.error('获取用户状态失败:', error));
}

// 页面加载时初始化布局
document.addEventListener('DOMContentLoaded', createLayout); 