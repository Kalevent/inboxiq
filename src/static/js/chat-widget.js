(function() {
  'use strict';

  // Get account config from embed code
  const account = window.InboxIQ?.account || '2';
  const config = window.InboxIQ?.config || {};
  const welcomeMessage = config.welcomeMessage || 'Hi! How can we help?';
  const captureLeads = config.captureLeads !== false;
  const requireEmail = config.requireEmail !== false;
  const primaryColor = config.primaryColor || '#6366f1';

  // Widget state
  let isOpen = false;
  let hasSubmittedLead = false;
  let visitorInfo = {};

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
          border-radius: 50%;
          background: ${primaryColor};
          color: white;
          border: none;
          cursor: pointer;
          box-shadow: 0 4px 12px rgba(0,0,0,0.15);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 24px;
          z-index: 999999;
          transition: transform 0.2s;
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
          padding: 16px;
          font-weight: 600;
          display: flex;
          justify-content: space-between;
          align-items: center;
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
        💬
      </button>

      <div id="inboxiq-chat-window">
        <div id="inboxiq-chat-header">
          <span>Chat with us</span>
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
      },
    };

    try {
      // Use public chat endpoint (no auth required)
      const response = await fetch('/api/v1/chat/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        hasSubmittedLead = true;
        return true;
      }
      return false;
    } catch (err) {
      console.error('InboxIQ chat error:', err);
      return false;
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
  }

  // Handle form submission
  function handleSubmit(event) {
    event.preventDefault();

    const name = document.getElementById('inboxiq-name')?.value || '';
    const email = document.getElementById('inboxiq-email')?.value || '';
    const company = document.getElementById('inboxiq-company')?.value || '';
    const message = document.getElementById('inboxiq-message').value;

    if (!message.trim()) return;

    // Store visitor info
    if (captureLeads && !hasSubmittedLead) {
      visitorInfo = { name, email, company };
    }

    // Add user message to UI
    addMessage(message, false);

    // Send to backend
    sendMessage(name, email, company, message).then(success => {
      if (success) {
        addMessage('Thanks! We\'ll get back to you soon.', true);

        // Hide lead form after first submission
        if (captureLeads) {
          document.getElementById('inboxiq-lead-form').style.display = 'none';
        }
      } else {
        addMessage('Sorry, something went wrong. Please try again.', true);
      }
    });

    // Clear message input
    document.getElementById('inboxiq-message').value = '';
  }

  // Initialize widget
  function init() {
    createWidget();

    // Event listeners
    document.getElementById('inboxiq-chat-bubble').addEventListener('click', toggleChat);
    document.getElementById('inboxiq-chat-close').addEventListener('click', toggleChat);
    document.getElementById('inboxiq-chat-form').addEventListener('submit', handleSubmit);

    console.log('InboxIQ chat widget loaded for account:', account);
  }

  // Load widget when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
