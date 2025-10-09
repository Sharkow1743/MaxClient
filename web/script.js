let currentChatId = null;
let isLoadingMore = false; // Flag to prevent multiple simultaneous loads


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

// MODIFICATION #1: Make navToChat an async function and track chat ID
async function navToChat(chatId) {
    currentChatId = chatId; // Set the active chat ID
    // We now await the navigation call to ensure the backend has the data
    // before the UI tries to refresh.
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
        // Use an anonymous async function for the click handler
        chatElement.onclick = async () => await navToChat(chatId);
        chatList.appendChild(chatElement);
    }
}

function refreshChatHistory(data) {
    // Destructure the new profilesInChat object from the data payload
    const { chatId, messages, profile, chats, profilesInChat } = data;
    const historyContent = document.getElementById('history-content');
    historyContent.innerHTML = '';

    const chatTitle = chats[chatId]?.title || `Chat ${chatId}`;
    document.getElementById('chat-title').innerText = chatTitle;

    messages.forEach(msg => {
        const senderId = String(msg.sender);
        let senderName = 'You';

        if (profile && senderId !== String(profile.id)) {
            // --- NEW, SIMPLIFIED LOGIC ---
            // Directly and synchronously look up the profile from the pre-loaded data.
            const senderProfile = profilesInChat[senderId];
            
            // This is a robust way to get the name, preventing errors.
            if (senderProfile && Array.isArray(senderProfile.names)) {
                // Prefer the name at index 1, but fall back to index 0, then a default.
                const nameInfo = senderProfile.names[0];
                senderName = `${nameInfo.firstName} ${nameInfo.lastName}` || nameInfo.name || `User ${senderId}`;
            } else {
                senderName = `User ${senderId}`; // Fallback if profile is missing
            }
            // --- END OF NEW LOGIC ---
        }

        const text = msg.text || '[NO_TEXT]';

        const messageElement = document.createElement('div');
        messageElement.className = 'message';
        const safeSender = senderName.replace(/</g, "&lt;").replace(/>/g, "&gt;");
        const safeText = text.replace(/</g, "&lt;").replace(/>/g, "&gt;");
        messageElement.innerHTML = `<div class="sender">${safeSender}</div><div class="text">${safeText}</div>`;
        historyContent.appendChild(messageElement);
    });

    // This remains the default behavior for new messages or navigating to a new chat.
    // The infinite scroll logic will override this when it needs to.
    const history = document.getElementById('history');
    history.scrollTop = history.scrollHeight;
}

function showMainView() {
    document.getElementById('auth-status').innerText = 'Login successful!';
    setTimeout(() => {
        document.getElementById('auth-view').style.display = 'none';
        document.getElementById('main-view').style.display = 'flex';
    }, 500);
}

document.getElementById('input-text').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// --- NEW INFINITE SCROLL LOGIC ---
const historyElement = document.getElementById('history');

historyElement.addEventListener('scroll', async () => {
    // If the user has scrolled to the top and we're not already loading more messages...
    if (historyElement.scrollTop === 0 && !isLoadingMore) {
        if (!currentChatId) return; // Exit if no chat is active

        isLoadingMore = true;
        const oldScrollHeight = historyElement.scrollHeight;

        // 1. Call the backend to load more messages into its internal state.
        await window.pywebview.api.load_more_messages(currentChatId);

        const newScrollHeight = historyElement.scrollHeight;
        historyElement.scrollTop = newScrollHeight - oldScrollHeight;

        isLoadingMore = false; // Reset the flag
    }
});