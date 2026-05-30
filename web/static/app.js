(function () {
    const chatArea = document.getElementById('chatArea');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');

    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = (Math.random() * 16) | 0;
            const v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    const sessionId = generateUUID();

    function scrollToBottom() {
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function addMessage(content, type, skillUsed) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', type);

        const bubble = document.createElement('div');
        bubble.classList.add('message-bubble');
        bubble.textContent = content;
        messageDiv.appendChild(bubble);

        if (skillUsed) {
            const badge = document.createElement('span');
            badge.classList.add('skill-badge');
            badge.textContent = skillUsed;
            messageDiv.appendChild(badge);
        }

        chatArea.appendChild(messageDiv);
        scrollToBottom();
    }

    function showTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.classList.add('typing-indicator');
        indicator.id = 'typingIndicator';
        indicator.innerHTML = '<span></span><span></span><span></span>';
        chatArea.appendChild(indicator);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;

        addMessage(message, 'user');
        messageInput.value = '';
        sendBtn.disabled = true;

        showTypingIndicator();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, session_id: sessionId })
            });

            removeTypingIndicator();

            if (!response.ok) {
                const errorData = await response.json();
                addMessage('Error: ' + (errorData.detail || 'Something went wrong'), 'bot');
                return;
            }

            const data = await response.json();
            addMessage(data.reply, 'bot', data.skill_used);
        } catch (error) {
            removeTypingIndicator();
            addMessage('Connection error. Please try again.', 'bot');
        } finally {
            sendBtn.disabled = false;
            messageInput.focus();
        }
    }

    sendBtn.addEventListener('click', sendMessage);

    messageInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    messageInput.focus();
})();
