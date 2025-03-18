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
        const response = await fetch('/api/user/check-login');
        const data = await response.json();
        
        if (!data.logged_in) {
            window.location.href = '/auth';
            return false;
        }
        return true;
    } catch (error) {
        console.error('检查登录状态失败:', error);
        window.location.href = '/auth';
        return false;
    }
}

// Toast 通知函数
function showToast(title, message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
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
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// 登出功能
async function logout() {
    try {
        const response = await fetch('/api/logout', {
            method: 'POST',
            credentials: 'include'
        });
        if (response.ok) {
            window.location.href = '/auth';
        }
    } catch (error) {
        console.error('登出失敗:', error);
        showToast('錯誤', '登出失敗', 'error');
    }
}

// 页面初始化
async function initializePage() {
    try {
        // 检查登录状态
        const isLoggedIn = await checkLoginStatus();
        if (!isLoggedIn) {
            return;
        }

        // 设置活动菜单
        setActiveMenu();

        // 加载用户信息
        await loadUserInfo();

    } catch (error) {
        console.error('页面初始化失败:', error);
        showToast('錯誤', '頁面初始化失敗', 'error');
    }
}

// 页面加载时执行初始化
document.addEventListener('DOMContentLoaded', initializePage);

