// 設置當前活動菜單項
function setActiveMenu() {
    const path = window.location.pathname;
    const menuItems = document.querySelectorAll('.nav-item');
    
    menuItems.forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('href') === path) {
            item.classList.add('active');
        }
    });
}

// 獲取用戶信息
async function loadUserInfo() {
    try {
        const response = await fetch('/api/user/info', {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (data.error) {
            console.error('Error in response:', data.error);
            return false;
        }
        
        if (data.username) {
            document.getElementById('user-fullname').textContent = data.username;
            const avatar = document.querySelector('.user-avatar');
            avatar.textContent = data.username[0].toUpperCase();
            return true;
        }
        
        return false;
    } catch (error) {
        console.error('獲取用戶信息失敗:', error);
        return false;
    }
}

// 检查登录状态
async function checkLoginStatus() {
    try {
        const response = await fetch('/api/user/info', {
            credentials: 'include'
        });
        const data = await response.json();
        
        console.log('登录检查结果:', {
            path: window.location.pathname,
            response: data
        });
        
        // 如果返回用户信息，说明已登录
        if (data.username) {
            // 如果在登录页面且已登录，重定向到控制台
            if (window.location.pathname.includes('/auth')) {
                window.location.href = '/dashboard';
            }
            return true;
        }
        
        console.error('未登录或会话已过期');
        // 如果不在登录页面，重定向到登录页
        if (!window.location.pathname.includes('/auth')) {
            window.location.href = '/auth';
        }
        return false;
        
    } catch (error) {
        console.error('检查登录状态失败:', error);
        console.log('错误详情:', {
            error: error,
            path: window.location.pathname
        });
        // 发生错误时，如果不在登录页面，重定向到登录页
        if (!window.location.pathname.includes('/auth')) {
            window.location.href = '/auth';
        }
        return false;
    }
}

// Toast 通知函数
function showToast(title, message, type = 'info', duration = 3000) {
    let toastContainer = document.getElementById('toastContainer');
    
    // 如果容器不存在，创建一个
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toastContainer';
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    toast.innerHTML = `
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <span class="toast-close" onclick="this.parentElement.remove()">×</span>
    `;
    
    toastContainer.appendChild(toast);
    
    // 确保 toast 显示
    toast.style.display = 'flex';
    
    setTimeout(() => {
        toast.remove();
    }, duration);
}

// 登出功能
async function logout() {
    try {
        // 先显示确认对话框
        if (!confirm('確定要退出登錄嗎？')) {
            return;
        }

        // 调用登出 API
        const response = await fetch('/api/logout', {
            method: 'POST',
            credentials: 'include'
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || '登出失敗');
        }

        // 清除本地存储的任何用户相关数据
        localStorage.clear();
        sessionStorage.clear();

        // 显示成功消息并确保它显示
        showToast('成功', '已安全退出登錄', 'success');

        // 延迟跳转时间加长，确保用户能看到提示
        setTimeout(() => {
            window.location.href = '/auth';
        }, 2000);

    } catch (error) {
        console.error('登出失敗:', error);
        showToast('錯誤', error.message || '登出失敗', 'error');
    }
}

// 页面初始化
async function initializePage() {
    try {
        console.log('开始初始化页面');
        console.log('当前路径:', window.location.pathname);
        
        // 检查登录状态
        const isLoggedIn = await checkLoginStatus();
        console.log('登录状态:', isLoggedIn);
        
        if (!isLoggedIn) {
            console.log('未登录，初始化终止');
            return;
        }

        // 设置活动菜单
        setActiveMenu();
        console.log('菜单设置完成');

        // 加载用户信息
        const userInfoResult = await loadUserInfo();
        console.log('用户信息加载结果:', userInfoResult);

    } catch (error) {
        console.error('页面初始化失败:', error);
        console.log('初始化错误详情:', error);
    }
}

// 页面加载时执行初始化
document.addEventListener('DOMContentLoaded', initializePage);

// 获取版本功能对照的HTML
function getVersionCompareHtml() {
    return `
        <div class="version-info">
            <div style="margin-bottom: 8px; font-weight: 500;">版本功能對照：</div>
            <div style="color: #666; font-size: 13px; line-height: 1.6;">
                <div style="margin-bottom: 8px;">
                    <span style="color: #666666;">基礎版 v1：</span>
                    <div style="padding-left: 12px;">
                        • 基礎功能
                    </div>
                </div>
                <!--<div style="margin-bottom: 8px;">
                    <span style="color: #1890ff;">進階版 v2：</span>
                    <div style="padding-left: 12px;">
                        • CRM客戶管理<br>
                        • Line機器人整合
                    </div>
                </div>-->
                <div>
                    <span style="color: #fa8c16;">進階版 v3：</span>
                    <div style="padding-left: 12px;">
                        • CRM客戶管理<br>
                        • Line機器人整合<br>
                        • 完整訂單管理<br>
                        • 工單二維碼系統
                    </div>
                </div>
            </div>
        </div>
    `;
}

// 添加版本信息弹出框的样式
const versionInfoStyle = `
    <style>
        .upgrade-btn-wrapper {
            position: relative;
            display: inline-block;
        }
        .version-info {
            display: none;
            position: absolute;
            top: 100%;
            left: 0;
            margin-top: 8px;
            background: white;
            border: 1px solid #e8e8e8;
            border-radius: 4px;
            padding: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            z-index: 1000;
            width: 280px;
        }
        .upgrade-btn-wrapper:hover .version-info {
            display: block;
        }
    </style>
`;

// 将样式添加到页面
document.head.insertAdjacentHTML('beforeend', versionInfoStyle);

