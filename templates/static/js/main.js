// 通用函数
document.addEventListener('DOMContentLoaded', function() {
    // 初始化代码
});

// 创建问卷页面逻辑
function addOption(button) {
    const optionDiv = document.createElement('div');
    optionDiv.className = 'option';
    optionDiv.innerHTML = `
        <input type="text" placeholder="选项内容" required>
        <button type="button" class="btn" onclick="addOption(this)">+</button>
        <button type="button" class="btn danger" onclick="this.parentElement.remove()">-</button>
    `;
    button.parentElement.parentElement.insertBefore(optionDiv, button.parentElement.nextSibling);
}

// 表单提交处理
document.getElementById('surveyForm')?.addEventListener('submit', function(e) {
    e.preventDefault();
    
    // 收集数据
    const formData = new FormData(this);
    
    // 验证逻辑
    let isValid = true;
    document.querySelectorAll('[required]').forEach(input => {
        if (!input.value.trim()) {
            isValid = false;
            input.classList.add('error');
        } else {
            input.classList.remove('error');
        }
    });
    
    if (isValid) {
        this.submit();
    }
});