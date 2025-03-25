// 创建公共布局
function createLayout() {
    // 插入布局
    insertLayout();
    
    // 等待一小段时间确保DOM已更新
    setTimeout(() => {
        // 根据当前页面设置活动菜单项
        const currentPath = window.location.pathname;
        const navItems = {
            '/dashboard/index.html': 'nav-dashboard',
            '/dashboard/instance.html': 'nav-instance',
            '/dashboard/profile.html': 'nav-profile',
            '/dashboard/message.html': 'nav-message'  // 添加站內信頁面
        };
        
        const activeNavId = navItems[currentPath];
        if (activeNavId) {
            const activeElement = document.getElementById(activeNavId);
            if (activeElement) {
                activeElement.classList.add('active');
            }
        }
    }, 0);
}

// 更新用户状态显示
async function updateUserStatus(status) {
    const statusText = status === 0 ? '超级用户' : '普通用户';
    const statusEl = document.getElementById('user-status');
    if (statusEl) {
        if (status !== 0) {
            try {
                // 检查是否有未处理的权限申请
                const response = await fetch('/api/message/list');
                const data = await response.json();
                const hasPendingRequest = data.messages.some(message => 
                    message.subject === '用戶權限申請' && 
                    message.status !== 'done'
                );

                if (hasPendingRequest) {
                    statusEl.innerHTML = `
                        ${statusText}
                        <button disabled 
                            style="margin-left: 8px; 
                            padding: 4px 8px; 
                            background: #d9d9d9; 
                            color: rgba(0,0,0,0.45); 
                            border: none; 
                            border-radius: 4px; 
                            font-size: 12px;">
                            已申請提升權限，請耐心等待
                        </button>
                    `;
                } else {
                    statusEl.innerHTML = `
                        ${statusText}
                        <button onclick="requestUpgrade()" 
                            style="margin-left: 8px; 
                            padding: 4px 8px; 
                            background: #1890ff; 
                            color: white; 
                            border: none; 
                            border-radius: 4px; 
                            cursor: pointer;
                            font-size: 12px;">
                            申請提升權限
                        </button>
                    `;
                }
            } catch (error) {
                console.error('檢查權限申請狀態失敗:', error);
                // 出错时显示正常按钮
                statusEl.innerHTML = `
                    ${statusText}
                    <button onclick="requestUpgrade()" 
                        style="margin-left: 8px; 
                        padding: 4px 8px; 
                        background: #1890ff; 
                        color: white; 
                        border: none; 
                        border-radius: 4px; 
                        cursor: pointer;
                        font-size: 12px;">
                        申請提升權限
                    </button>
                `;
            }
        } else {
            statusEl.textContent = statusText;
        }
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
                <a href="/dashboard/instance.html" class="nav-item" id="nav-instance">
                    <i class="material-icons">dns</i>
                    實例管理
                </a>
            </li>
            <li>
                <a href="/dashboard/message.html" class="nav-item" id="nav-message">
                    <i class="material-icons">mail</i>
                    站內信
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

    // 获取用户信息并添加控制台菜单（如果是管理员）
    fetch('/api/user/info')
        .then(response => response.json())
        .then(data => {
            if (data.id === 1) {
                const navMenu = sidebar.querySelector('.nav-menu');
                const dashboardItem = document.createElement('li');
                dashboardItem.innerHTML = `
                    <a href="/dashboard/index.html" class="nav-item" id="nav-dashboard">
                        <i class="material-icons">dashboard</i>
                        控制台
                    </a>
                `;
                navMenu.insertBefore(dashboardItem, navMenu.firstChild);
            }
        })
        .catch(error => console.error('获取用户信息失败:', error));

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

// 全局消息通知系统
const messageNotification = {
    lastStatus: new Map(),
    pollingInterval: null,

    // 从 localStorage 获取已知消息
    getKnownMessages() {
        const stored = localStorage.getItem('knownMessages');
        return stored ? new Set(JSON.parse(stored)) : new Set();
    },

    // 保存已知消息到 localStorage
    saveKnownMessages(messages) {
        localStorage.setItem('knownMessages', JSON.stringify([...messages]));
    },

    getStatusText(status) {
        const statusTexts = {
            'unread': '<span style="color: #ff4d4f">未讀</span>，請耐心等待',
            'read': '<span style="color: #1890ff">已讀</span>，請耐心等待', 
            'processing': '<span style="color: #722ed1">處理中</span>，請耐心等待',
            'done': '<span style="color: #52c41a">已處理</span>'
        };
        return statusTexts[status] || status;
    },

    async checkUpdates() {
        try {
            const response = await fetch('/api/message/list');
            const data = await response.json();
            
            // 获取已知消息
            const knownMessages = this.getKnownMessages();
            
            // 检查新消息
            data.messages.forEach(message => {
                if (!knownMessages.has(message.id)) {
                    // 这是一条新消息
                    showToast('新消息', `收到來自 ${message.sender_name} 的新消息：${message.subject}`, 'info', 5000);
                    knownMessages.add(message.id);
                }
            });
            
            // 保存更新后的已知消息
            this.saveKnownMessages(knownMessages);
            
            // 现有的状态更新检查
            data.messages.forEach(message => {
                const previousStatus = this.lastStatus.get(message.id);
                if (previousStatus && previousStatus !== message.status) {
                    showToast('通知', `消息 "${message.subject}" 狀態已更新為 ${this.getStatusText(message.status)}`, 'info', 5000);
                    
                    if (window.location.pathname === '/dashboard/message.html' && typeof loadMessages === 'function') {
                        loadMessages();
                    }
                }
                this.lastStatus.set(message.id, message.status);
            });
        } catch (error) {
            console.error('檢查消息更新失敗:', error);
        }
    },

    start() {
        if (!this.pollingInterval) {
            this.checkUpdates();
            this.pollingInterval = setInterval(() => this.checkUpdates(), 5000);
        }
    },

    stop() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }
};

// 在页面加载完成后初始化消息通知
document.addEventListener('DOMContentLoaded', () => {
    // 现有的初始化代码
    createLayout();
    
    // 启动消息通知
    messageNotification.start();

    setTimeout(checkExpiredInstances, 1000);
});

// 页面可见性变化时控制轮询
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        messageNotification.stop();
    } else {
        messageNotification.start();
    }
});

// 页面关闭时停止轮询
window.addEventListener('beforeunload', () => {
    messageNotification.stop();
});

// 修改申请升级函数
window.requestUpgrade = async function() {
    try {
        // 获取用户信息
        const userResponse = await fetch('/api/user/info');
        const userData = await userResponse.json();
        
        // 构造邮件内容
        const messageData = {
            receiver_id: 1,
            priority: 'urgent',
            subject: '用戶權限申請',
            content: `
用戶權限提升申請：

用戶信息：
- 用戶名：${userData.username}
- 郵箱：${userData.email}
- 電話：${userData.phone || '未填寫'}


- 註冊時間：${userData.created_at}
- 當前狀態：${userData.status === 0 ? '超级用户' : '普通用户'}
            `.trim()
        };

        // 发送消息
        const response = await fetch('/api/message/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(messageData)
        });

        if (response.ok) {
            showToast('成功', '權限申請已發送，請耐心等待管理員處理', 'success', 5000);
            // 立即更新状态显示
            const userResponse = await fetch('/api/user/info');
            const userData = await userResponse.json();
            await updateUserStatus(userData.status);
        } else {
            throw new Error('發送申請失敗');
        }
    } catch (error) {
        console.error('申請提升權限失敗:', error);
        showToast('錯誤', '申請提升權限失敗，請稍後重試', 'error');
    }
};

// 添加检查实例过期的函数
async function checkExpiredInstances() {
    try {
        // 先获取用户信息
        const userResponse = await fetch('/api/user/info');
        const userData = await userResponse.json();
        
        // 如果是管理员（ID=1），不显示提示
        if (userData.id === 1) {
            return;
        }

        const response = await fetch('/api/instance/list');
        const data = await response.json();
        
        if (data.instances && data.instances.length > 0) {
            // 检查过期实例
            const expiredInstance = data.instances.find(instance => instance.status === 3);
            if (expiredInstance) {
                // 计算销毁日期
                const expiresAt = new Date(expiredInstance.expires_at);
                const destroyDate = new Date(expiresAt.getTime() + 30 * 24 * 60 * 60 * 1000);
                const dateStr = `${destroyDate.getFullYear()}年${destroyDate.getMonth() + 1}月${destroyDate.getDate()}日`;
                
                showToast(
                    '实例已过期', 
                    `您的实例已停止运行。系统将在 ${dateStr} 自动销毁此实例。如需继续使用，请及时聯繫管理員。`,
                    'error',
                    10000
                );
            }
            
            // 检查即将过期的实例
            const runningInstance = data.instances.find(instance => instance.status === 1);
            if (runningInstance) {
                const expiresAt = new Date(runningInstance.expires_at);
                const now = new Date();
                const daysToExpire = Math.ceil((expiresAt - now) / (1000 * 60 * 60 * 24));
                
                if (daysToExpire <= 7 && daysToExpire > 0) {
                    showToast(
                        '实例即将过期', 
                        `您的实例将在 ${daysToExpire} 天后过期。为避免服务中断，请及时聯繫管理員。`,
                        'warning',
                        10000
                    );
                }
            }
        }
    } catch (error) {
        console.error('检查实例状态失败:', error);
    }
}