const popupStyles = `
    .popup {
        display: none;
        position: fixed;
        left: 0;
        top: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.5);
        justify-content: center;
        align-items: center;
        z-index: 1000;
    }
    .popup-content {
        background-color: #fff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
        width: 300px;
        text-align: center;
        position: relative;
    }
    .close-btn {
        position: absolute;
        top: 10px;
        right: 15px;
        font-size: 24px;
        cursor: pointer;
        color: #888;
    }
    .close-btn:hover {
        color: #000;
    }
    #popupMessage {
        margin-bottom: 20px;
        font-size: 16px;
    }
    #confirmBtn {
        padding: 10px 20px;
        background-color: #007bff;
        color: #fff;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-size: 14px;
    }
    #confirmBtn:hover {
        background-color: #0056b3;
    }
`;

// 动态创建样式标签并插入到文档中
const styleTag = document.createElement('style');
styleTag.textContent = popupStyles;
document.head.appendChild(styleTag);

// 动态创建弹窗结构
function createPopup() {
    const popup = document.createElement('div');
    popup.id = 'customPopup';
    popup.className = 'popup';

    const popupContent = document.createElement('div');
    popupContent.className = 'popup-content';

    const closeBtn = document.createElement('span');
    closeBtn.className = 'close-btn';
    closeBtn.innerHTML = '&times;';
    closeBtn.onclick = closePopup;

    const message = document.createElement('p');
    message.id = 'popupMessage';
    message.textContent = '这是一个动态创建的弹窗！';

    const confirmBtn = document.createElement('button');
    confirmBtn.id = 'confirmBtn';
    confirmBtn.textContent = '确定';
    confirmBtn.onclick = closePopup;

    // 将元素添加到弹窗内容中
    popupContent.appendChild(closeBtn);
    popupContent.appendChild(message);
    popupContent.appendChild(confirmBtn);

    // 将弹窗内容添加到弹窗中
    popup.appendChild(popupContent);

    // 将弹窗添加到页面中
    document.body.appendChild(popup);

    return popup;
}

// 显示弹窗的函数
function showPopup(message) {
    let popup = document.getElementById('customPopup');
    if (!popup) {
        // 如果弹窗不存在，则创建弹窗
        createPopup();
        // 重新获取弹窗元素
        popup = document.getElementById('customPopup');
    }
    const popupMessage = document.getElementById('popupMessage');
    if (popupMessage) {
        popupMessage.textContent = message;
    }
    if (popup) {
        popup.style.display = 'flex';
    } else {
        console.error("弹窗元素未找到！");
    }
}

// 关闭弹窗的函数
function closePopup() {
    const popup = document.getElementById('customPopup');
    if (popup) {
        popup.style.display = 'none';
    }
}

// 点击弹窗外部关闭弹窗
window.addEventListener('click', (event) => {
    const popup = document.getElementById('customPopup');
    if (event.target === popup) {
        closePopup();
    }
});

console.log("popup.js loaded!");