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
        console.log('Fetching user info...');  // 添加日志
        const response = await fetch('/api/user/info', {
            credentials: 'include'
        });
        const data = await response.json();
        console.log('Received user data:', data);  // 添加日志
        
        if (data.error) {
            console.log('Error in response:', data.error);
            return false;
        }
        
        if (data.username) {
            console.log('Username found:', data.username);  // 添加日志
            document.getElementById('user-fullname').textContent = data.username;
            const avatar = document.querySelector('.user-avatar');
            avatar.textContent = data.username[0].toUpperCase();
            return true;
        }
        
        console.log('No username in response data');  // 添加日志
        return false;
    } catch (error) {
        console.error('獲取用戶信息失敗:', error);
        return false;
    }
}

// 将函数声明移到全局作用域
window.checkLoginStatus = async function() {
    try {
        const response = await fetch('/api/user/check-login');
        const data = await response.json();
        
        if (!data.logged_in) {
            console.log('checkLoginStatus: 用户未登录');  // 先打印日志
            return false;
        }
        return true;
    } catch (error) {
        console.error('检查登录状态失败:', error);
        return false;
    }
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
    }
}

// 頁面加載時執行
document.addEventListener('DOMContentLoaded', async () => {
    setActiveMenu();
    const isLoggedIn = await loadUserInfo();
    if (!isLoggedIn) {
        console.log('页面加载时检测到未登录');
        // 暂时注释掉重定向，先看看具体返回了什么
        // window.location.href = '/auth';
    } else {
        console.log('用户已登录');  // 添加登录成功的日志
    }
}); 