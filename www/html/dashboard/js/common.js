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
        const response = await fetch('/api/user/info');
        if (response.ok) {
            const data = await response.json();
            document.getElementById('user-fullname').textContent = data.username;
            const avatar = document.querySelector('.user-avatar');
            avatar.textContent = data.username[0].toUpperCase();
        }
    } catch (error) {
        console.error('獲取用戶信息失敗:', error);
    }
}

// 登出功能
async function logout() {
    try {
        const response = await fetch('/api/logout', {
            method: 'POST'
        });
        if (response.ok) {
            window.location.href = '/auth';
        }
    } catch (error) {
        console.error('登出失敗:', error);
    }
}

// 頁面加載時執行
document.addEventListener('DOMContentLoaded', () => {
    setActiveMenu();
    loadUserInfo();
}); 