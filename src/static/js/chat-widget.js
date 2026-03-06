(function() {
  'use strict';

  // Get account config from embed code
  const account = window.InboxIQ?.account || '2';
  const config = window.InboxIQ?.config || {};
  const welcomeMessage = config.welcomeMessage || 'Hi! How can we help?';
  const captureLeads = config.captureLeads !== false;
  const requireEmail = config.requireEmail !== false;
  const primaryColor = config.primaryColor || '#6366f1';
  const logoUrl = (typeof config.logoUrl === 'string' && config.logoUrl.length > 0)
    ? config.logoUrl : null;
  // Optional custom chatbot webhook. Must be https:// to be used.
  const webhookUrl = (typeof config.webhookUrl === 'string' && config.webhookUrl.startsWith('https://'))
    ? config.webhookUrl : null;

  // Widget state
  let isOpen = false;
  let hasSubmittedLead = false;
  let visitorInfo = {};
  let conversationHistory = []; // [{role: 'user'|'assistant', content: '...'}]

  // Create widget HTML
  function createWidget() {
    const widget = document.createElement('div');
    widget.id = 'inboxiq-chat-widget';
    widget.innerHTML = `
      <style>
        #inboxiq-chat-bubble {
          position: fixed;
          bottom: 20px;
          right: 80px;
          width: 60px;
          height: 60px;
          border-radius: 16px;
          background: transparent;
          border: none;
          cursor: pointer;
          box-shadow: 0 4px 12px rgba(0,0,0,0.25);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 0;
          z-index: 999999;
          transition: transform 0.2s;
          overflow: hidden;
        }
        #inboxiq-chat-bubble img {
          width: 60px;
          height: 60px;
          display: block;
        }
        #inboxiq-chat-bubble:hover {
          transform: scale(1.05);
        }
        @media (max-width: 640px) {
          #inboxiq-chat-bubble {
            right: 20px;
            bottom: 76px;
          }
        }
        #inboxiq-chat-window {
          position: fixed;
          bottom: 100px;
          right: 24px;
          width: 380px;
          max-width: calc(100vw - 48px);
          height: 600px;
          max-height: calc(100vh - 140px);
          background: white;
          border-radius: 16px;
          box-shadow: 0 8px 32px rgba(0,0,0,0.2);
          z-index: 999998;
          display: none;
          flex-direction: column;
          overflow: hidden;
        }
        #inboxiq-chat-window.open {
          display: flex;
        }
        #inboxiq-chat-header {
          background: ${primaryColor};
          color: white;
          padding: 12px 16px;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        #inboxiq-chat-header-title {
          flex: 1;
          font-size: 15px;
        }
        #inboxiq-chat-logo {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          object-fit: contain;
          background: white;
          padding: 5px;
          flex-shrink: 0;
          box-shadow: 0 1px 4px rgba(0,0,0,0.25);
        }
        #inboxiq-chat-close {
          background: none;
          border: none;
          color: white;
          font-size: 24px;
          cursor: pointer;
          padding: 0;
          width: 32px;
          height: 32px;
        }
        #inboxiq-chat-messages {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
          background: #f9fafb;
        }
        .inboxiq-message {
          margin-bottom: 12px;
          padding: 12px;
          border-radius: 8px;
          max-width: 80%;
        }
        .inboxiq-message.bot {
          background: #e5e7eb;
          color: #1f2937;
          margin-right: auto;
        }
        .inboxiq-message.user {
          background: ${primaryColor};
          color: white;
          margin-left: auto;
        }
        #inboxiq-chat-form {
          padding: 16px;
          border-top: 1px solid #e5e7eb;
          background: white;
        }
        #inboxiq-chat-form input,
        #inboxiq-chat-form textarea {
          width: 100%;
          padding: 10px;
          border: 1px solid #d1d5db;
          border-radius: 8px;
          margin-bottom: 8px;
          font-family: inherit;
          font-size: 14px;
          background: white;
          color: #1f2937;
          pointer-events: auto;
          user-select: text;
          -webkit-user-select: text;
          cursor: text;
          -webkit-appearance: none;
          appearance: none;
          outline: none;
        }
        #inboxiq-chat-form input:focus,
        #inboxiq-chat-form textarea:focus {
          border-color: ${primaryColor};
          outline: 2px solid ${primaryColor};
          outline-offset: -1px;
        }
        #inboxiq-chat-form button {
          width: 100%;
          padding: 10px;
          background: ${primaryColor};
          color: white;
          border: none;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
        }
        #inboxiq-chat-form button:hover {
          opacity: 0.9;
        }
      </style>

      <button id="inboxiq-chat-bubble" aria-label="Open chat">
        ${logoUrl ? `<img src="${logoUrl}" alt="Open chat">` : '💬'}
      </button>

      <div id="inboxiq-chat-window">
        <div id="inboxiq-chat-header">
          ${logoUrl ? `<img id="inboxiq-chat-logo" src="${logoUrl}" alt="Logo">` : ''}
          <span id="inboxiq-chat-header-title">InboxIQ Agent</span>
          <button id="inboxiq-chat-close" aria-label="Close chat">×</button>
        </div>

        <div id="inboxiq-chat-messages">
          <div class="inboxiq-message bot">${welcomeMessage}</div>
        </div>

        <form id="inboxiq-chat-form">
          <div id="inboxiq-lead-form" style="display: ${captureLeads ? 'block' : 'none'};">
            <input type="text" id="inboxiq-name" placeholder="Your name" required />
            <input type="email" id="inboxiq-email" placeholder="Your email" ${requireEmail ? 'required' : ''} />
            <input type="text" id="inboxiq-company" placeholder="Company (optional)" />
          </div>
          <textarea id="inboxiq-message" placeholder="Type your message..." rows="3" required></textarea>
          <button type="submit">Send</button>
        </form>
      </div>
    `;
    document.body.appendChild(widget);
  }

  // Toggle chat window
  function toggleChat() {
    isOpen = !isOpen;
    const chatWindow = document.getElementById('inboxiq-chat-window');
    if (isOpen) {
      chatWindow.classList.add('open');
    } else {
      chatWindow.classList.remove('open');
    }
  }

  // Send message to InboxIQ
  async function sendMessage(name, email, company, message) {
    const payload = {
      subject: `Chat from ${name || email || 'Visitor'}`,
      body: message,
      source: 'chat',
      provider: 'inboxiq',
      message_id: `chat-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      from_email: email || `chat-visitor-${Date.now()}@inboxiq.local`,
      context: {
        name: name,
        email: email,
        company: company,
        account_id: account,
        capture_lead: captureLeads && !hasSubmittedLead,
        page_url: window.location.href,
        history: conversationHistory.slice(-10), // last 5 exchanges
      },
    };

    try {
      let endpoint, body;

      if (webhookUrl) {
        // Custom chatbot webhook — send a clean payload the developer controls
        endpoint = webhookUrl;
        body = JSON.stringify({
          message: message,
          context: {
            name: name,
            email: email,
            company: company,
            account_id: account,
            page_url: window.location.href,
          },
        });
      } else {
        // InboxIQ native endpoint
        endpoint = '/api/v1/chat/submit';
        body = JSON.stringify(payload);
      }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
      });

      if (response.ok) {
        const data = await response.json();
        hasSubmittedLead = true;
        return { ok: true, reply: data.reply || null };
      }
      return { ok: false, reply: null };
    } catch (err) {
      console.error('InboxIQ chat error:', err);
      return { ok: false, reply: null };
    }
  }

  // Add message to UI
  function addMessage(text, isBot = false) {
    const messagesDiv = document.getElementById('inboxiq-chat-messages');
    const msg = document.createElement('div');
    msg.className = `inboxiq-message ${isBot ? 'bot' : 'user'}`;
    msg.textContent = text;
    messagesDiv.appendChild(msg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return msg;
  }

  // Show a typing indicator bubble
  function addTypingIndicator() {
    const messagesDiv = document.getElementById('inboxiq-chat-messages');
    const typing = document.createElement('div');
    typing.className = 'inboxiq-message bot';
    typing.setAttribute('data-typing', 'true');
    typing.textContent = '…';
    messagesDiv.appendChild(typing);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return typing;
  }

  // Handle form submission
  function handleSubmit(event) {
    event.preventDefault();

    const name = document.getElementById('inboxiq-name')?.value || '';
    const email = document.getElementById('inboxiq-email')?.value || '';
    const company = document.getElementById('inboxiq-company')?.value || '';
    const messageInput = document.getElementById('inboxiq-message');
    const message = messageInput.value;
    const submitBtn = document.querySelector('#inboxiq-chat-form button[type="submit"]');

    if (!message.trim()) return;

    // Store visitor info
    if (captureLeads && !hasSubmittedLead) {
      visitorInfo = { name, email, company };
    }

    // Add user message to UI
    addMessage(message, false);

    // Disable input while waiting for AI reply
    if (submitBtn) submitBtn.disabled = true;
    messageInput.value = '';

    // Show typing indicator
    const typingEl = addTypingIndicator();

    // Send to backend
    sendMessage(name, email, company, message).then(result => {
      typingEl.remove();
      if (submitBtn) submitBtn.disabled = false;

      if (result.ok) {
        const reply = result.reply || "Thanks! We'll get back to you soon.";
        addMessage(reply, true);

        // Record this exchange in conversation history
        conversationHistory.push({ role: 'user', content: message });
        conversationHistory.push({ role: 'assistant', content: reply });

        // Hide lead form after first submission
        if (captureLeads) {
          const leadForm = document.getElementById('inboxiq-lead-form');
          if (leadForm) leadForm.style.display = 'none';
        }
      } else {
        addMessage('Sorry, something went wrong. Please try again.', true);
      }
    });
  }

  // Initialize widget
  function init() {
    createWidget();

    // Event listeners
    document.getElementById('inboxiq-chat-bubble').addEventListener('click', toggleChat);
    document.getElementById('inboxiq-chat-close').addEventListener('click', toggleChat);
    document.getElementById('inboxiq-chat-form').addEventListener('submit', handleSubmit);

    // Auto-open for visitors after a short delay
    setTimeout(toggleChat, 2500);

    console.log('InboxIQ chat widget loaded for account:', account);
  }

  // Load widget when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
