let currentChatId = null;
let isFullloaded = false; // Flag to prevent multiple simultaneous loads
let isLoading = false;

async function loadAttachment(element, chatId, messageId, attachInfo) {
    // Prevent multiple clicks while loading
    if (element.classList.contains('loading')) return;

    const originalContent = element.innerHTML;
    element.innerHTML = '<div class="spinner"></div>'; // Show loading indicator
    element.classList.add('loading');

    try {
        // Call the new backend API
        const response = await window.pywebview.api.get_attachment(chatId, messageId, attachInfo);

        if (response && response.data_uri) {
            // Replace the placeholder with the actual content
            let newElement;
            switch (attachInfo._type) {
                case 'PHOTO':
                    newElement = document.createElement('img');
                    newElement.className = 'attachment-image';
                    newElement.src = response.data_uri;
                    break;
                case 'VIDEO':
                    newElement = document.createElement('video');
                    newElement.className = 'attachment-video';
                    newElement.src = response.data_uri;
                    newElement.controls = true;
                    break;
                case 'FILE':
                    newElement = document.createElement('a');
                    newElement.className = 'attachment-file loaded';
                    newElement.href = response.data_uri;
                    newElement.download = response.filename || 'download';
                    newElement.innerText = `Download: ${response.filename || 'File'}`;
                    // For files, we might want to trigger the download immediately
                    newElement.click();
                    break;
                case _:
                    throw new Error("Unexpected attachment");
            }
            if (newElement) {
                element.parentNode.replaceChild(newElement, element);
            }
        } else {
            // Handle error case
            element.innerHTML = 'Error loading';
            element.classList.remove('loading');
        }
    } catch (e) {
        console.error("Failed to load attachment:", e);
        element.innerHTML = 'Error loading';
        element.classList.remove('loading');
    }
}

function startAuth() {
    const phone = document.getElementById('auth-phone').value;
    document.getElementById('auth-status').innerText = 'Sending code...';
    window.pywebview.api.start_auth(phone).then(response => {
        if (response.success) {
            document.getElementById('auth-status').innerText = 'Code sent! Enter it below.';
            document.getElementById('auth-code-group').style.display = 'block';
        } else {
            document.getElementById('auth-status').innerText = `Error: ${response.error}`;
        }
    });
}

function submitCode() {
    const code = document.getElementById('auth-code').value;
    document.getElementById('auth-status').innerText = 'Verifying code...';
    window.pywebview.api.submit_code(code).then(response => {
        if (!response.success) {
            document.getElementById('auth-status').innerText = 'Invalid code. Please try again.';
        }
    });
}

function sendMessage() {
    const text = document.getElementById('input-text').value;
    if (text.trim()) {
        window.pywebview.api.send_message(text).then(() => {
            document.getElementById('input-text').value = '';
        });
    }
}

async function navToChat(chatId) {
    currentChatId = chatId; // Set the active chat ID
    isFullloaded = false;
    await window.pywebview.api.nav_to_chat(chatId);
}

function loadChats(chats) {
    const chatList = document.getElementById('chat-list');
    chatList.innerHTML = '';
    for (const [chatId, chatInfo] of Object.entries(chats)) {
        const title = chatInfo.title || `Chat ${chatId}`;
        const chatElement = document.createElement('div');
        chatElement.className = 'chat-item';
        chatElement.innerText = title.length > 25 ? title.substring(0, 25) + '...' : title;
        chatElement.onclick = async () => await navToChat(chatId);
        chatList.appendChild(chatElement);
    }
}

function refreshChatHistory(data, scrollToBottom = true) {
    const { chatId, messages, profile, chats, profilesInChat } = data;
    const historyContent = document.getElementById('history-content');
    const historyElement = document.getElementById('history');
    const oldScrollHeight = historyElement.scrollHeight;

    if (scrollToBottom) {
        historyContent.innerHTML = '';
    }

    document.getElementById('chat-title').innerText = chats[chatId]?.title || `Chat ${chatId}`;

    messages.forEach(msg => {
        if (!scrollToBottom && document.getElementById(`msg-${msg.id}`)) return;

        const senderId = String(msg.sender);
        let senderName = 'You';
        if (profile && senderId !== String(profile.id)) {
            const senderProfile = profilesInChat[senderId];
            if (senderProfile && Array.isArray(senderProfile.names) && senderProfile.names.length > 0) {
                const nameInfo = senderProfile.names[0];
                senderName = `${nameInfo.firstName || ''} ${nameInfo.lastName || ''}`.trim() || nameInfo.name || `User ${senderId}`;
            } else {
                senderName = `User ${senderId}`;
            }
        }

        const text = msg.text || '';
        const messageElement = document.createElement('div');
        messageElement.className = 'message';
        messageElement.id = `msg-${msg.id}`;

        const safeSender = senderName.replace(/</g, "&lt;").replace(/>/g, "&gt;");
        const safeText = text.replace(/</g, "&lt;").replace(/>/g, "&gt;");

        if (safeText) {
            const messageContent = document.createElement('div');
            messageContent.className = 'message-content';
            messageContent.innerHTML = `<div class="sender">${safeSender}</div><div class="text">${safeText}</div>`;
            messageElement.appendChild(messageContent);
        }

        // --- NEW: LAZY LOADING ATTACHMENT RENDERING ---
        if (msg.attaches && Array.isArray(msg.attaches)) {
            const attachmentsContainer = document.createElement('div');
            attachmentsContainer.className = 'attachments-container';

            msg.attaches.forEach(attach => {
                // Create a placeholder div that will be replaced on click
                const placeholder = document.createElement('div');
                placeholder.className = 'attachment-placeholder';
                
                placeholder.onclick = () => loadAttachment(placeholder, chatId, msg.id, attach);

                let placeholderText = 'Attachment';
                switch (attach._type) {
                    case 'PHOTO': placeholderText = '📷 View Photo'; break;
                    case 'VIDEO': placeholderText = '▶️ Play Video'; break;
                    case 'FILE': placeholderText = `📄 Download ${attach.filename || 'File'}`; break;
                }
                placeholder.innerText = placeholderText;
                attachmentsContainer.appendChild(placeholder);
            });
            messageElement.appendChild(attachmentsContainer);
        }
        
        if (scrollToBottom) {
            historyContent.appendChild(messageElement);
        } else {
            historyContent.prepend(messageElement);
        }
    });

    if (scrollToBottom) {
        historyElement.scrollTop = historyElement.scrollHeight;
    } else {
        const newScrollHeight = historyElement.scrollHeight;
        historyElement.scrollTop = newScrollHeight - oldScrollHeight;
    }
}


function showMainView() {
    document.getElementById('auth-status').innerText = 'Login successful!';
    setTimeout(() => {
        document.getElementById('auth-view').style.display = 'none';
        document.getElementById('main-view').style.display = 'flex';
        window.pywebview.api.load_chats();
    }, 500);
}

document.getElementById('input-text').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

const historyElement = document.getElementById('history');


historyElement.addEventListener('scroll', async () => {
    if (isLoading) return;
    if (isFullloaded || !currentChatId) return;
    isLoading = true;
    if (historyElement.scrollTop == 0) {   
        const older_messages = await window.pywebview.api.load_more_messages(currentChatId);     
        if (older_messages.length == 0) {
            console.log("No more messages to load.")
            isFullloaded = true
        }
    }
    isLoading = false
});