(function () {
  'use strict';

  const account = window.InboxIQ?.account || '2';
  const primaryColor = window.InboxIQ?.config?.primaryColor || '#6366f1';
  const signupUrl = '/signup';
  const AVATAR_URL = '/static/img/aria-avatar.jpg';
  const SESSION_KEY = 'inboxiq_chat_v2';

  // ── State ────────────────────────────────────────────────────────────────
  // phase: closed | greeting | demo | talk_name | talk_email | talk_chat
  let state = { phase: 'closed', name: '', email: '', messages: [], dismissed: false };
  try { const s = sessionStorage.getItem(SESSION_KEY); if (s) state = JSON.parse(s); } catch (_) {}
  function persist() { try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(state)); } catch (_) {} }

  // ── CSS ──────────────────────────────────────────────────────────────────
  const CSS = `
    #iq-bubble {
      position: fixed; bottom: 20px; right: 24px; width: 60px; height: 60px;
      border-radius: 50%; border: none; cursor: pointer; padding: 0;
      box-shadow: 0 4px 14px rgba(0,0,0,0.25); z-index: 999999; overflow: visible;
      background: transparent; transition: transform .2s;
    }
    #iq-bubble:hover { transform: scale(1.05); }
    #iq-bubble-img { width: 60px; height: 60px; border-radius: 50%; display: block; }
    #iq-badge {
      position: absolute; top: -2px; right: -2px; width: 14px; height: 14px;
      border-radius: 50%; background: #ef4444; border: 2px solid white; display: none;
    }
    #iq-bubble.has-badge #iq-badge { display: block; }
    @media (max-width: 640px) { #iq-bubble { right: 16px; bottom: 72px; } }
    #iq-panel {
      position: fixed; bottom: 96px; right: 24px; width: 360px;
      max-width: calc(100vw - 32px); background: #fff; border-radius: 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.18); z-index: 999998;
      display: none; flex-direction: column; overflow: hidden;
      font-family: system-ui, -apple-system, sans-serif; font-size: 14px;
    }
    #iq-panel.open { display: flex; }
    @media (max-width: 640px) { #iq-panel { right: 8px; bottom: 144px; width: calc(100vw - 16px); } }
    .iq-hdr {
      background: ${primaryColor}; color: #fff; padding: 12px 16px;
      display: flex; align-items: center; gap: 10px; flex-shrink: 0;
    }
    .iq-hdr img { width: 40px; height: 40px; border-radius: 50%; }
    .iq-hdr-txt { flex: 1; }
    .iq-hdr-name { font-weight: 700; font-size: 15px; }
    .iq-hdr-sub { font-size: 11px; opacity: .8; }
    .iq-close { background: none; border: none; color: #fff; font-size: 22px; cursor: pointer; padding: 0; line-height: 1; }
    .iq-body { padding: 16px; }
    .iq-greeting { color: #374151; margin: 0 0 14px; line-height: 1.5; }
    .iq-cta {
      display: flex; align-items: center; gap: 10px; width: 100%;
      padding: 11px 14px; margin-bottom: 8px; border: 2px solid #e5e7eb;
      border-radius: 10px; background: #fff; font-size: 14px; font-weight: 600;
      color: #374151; cursor: pointer; text-align: left;
      transition: border-color .15s, background .15s;
    }
    .iq-cta:last-child { margin-bottom: 0; }
    .iq-cta:hover { border-color: ${primaryColor}; background: #f5f3ff; }
    .iq-icon { font-size: 18px; }
    .iq-msgs { max-height: 240px; overflow-y: auto; margin-bottom: 10px; }
    .iq-msg { padding: 9px 12px; border-radius: 10px; margin-bottom: 8px; max-width: 85%; line-height: 1.5; }
    .iq-msg.bot { background: #f3f4f6; color: #1f2937; margin-right: auto; }
    .iq-msg.user { background: ${primaryColor}; color: #fff; margin-left: auto; }
    .iq-msg.bot a { color: ${primaryColor}; }
    .iq-row { display: flex; gap: 8px; }
    .iq-inp {
      flex: 1; padding: 9px 12px; border: 1.5px solid #d1d5db; border-radius: 8px;
      font-size: 14px; background: #fff; color: #1f2937; outline: none; font-family: inherit;
    }
    .iq-inp:focus { border-color: ${primaryColor}; }
    .iq-send {
      padding: 9px 14px; background: ${primaryColor}; color: #fff; border: none;
      border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px;
    }
    .iq-send:disabled { opacity: .5; cursor: default; }
    .iq-err { font-size: 12px; color: #ef4444; margin: 4px 0 0; min-height: 16px; }
    .iq-soft { text-align: center; font-size: 13px; color: #6b7280; margin-top: 8px; }
    .iq-soft a { color: ${primaryColor}; font-weight: 600; text-decoration: none; }
  `;

  // ── DOM helpers ──────────────────────────────────────────────────────────
  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === 'on') Object.entries(v).forEach(([ev, fn]) => e.addEventListener(ev, fn));
        else e.setAttribute(k, v);
      }
    }
    if (children) (Array.isArray(children) ? children : [children]).forEach(c => {
      if (c == null) return;
      e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return e;
  }

  function mkMsg(text, role) {
    const m = el('div', { class: `iq-msg ${role}` });
    if (role === 'user') {
      m.textContent = text;
    } else {
      m.innerHTML = text;
    }
    return m;
  }

  function mkTyping() {
    return mkMsg('<span style="letter-spacing:.3em">···</span>', 'bot');
  }

  function mkInput(placeholder, type) {
    const inp = el('input', { class: 'iq-inp', type: type || 'text', placeholder: placeholder || '' });
    const btn = el('button', { class: 'iq-send', type: 'button' }, 'Send');
    const row = el('div', { class: 'iq-row' }, [inp, btn]);
    return { row, inp, btn };
  }

  function buildHeader(onClose) {
    return el('div', { class: 'iq-hdr' }, [
      el('img', { src: AVATAR_URL, alt: 'Aria' }),
      el('div', { class: 'iq-hdr-txt' }, [
        el('div', { class: 'iq-hdr-name' }, 'Aria'),
        el('div', { class: 'iq-hdr-sub' }, 'InboxIQ'),
      ]),
      el('button', { class: 'iq-close', 'aria-label': 'Close', on: { click: onClose } }, '×'),
    ]);
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function scrollMsgs(msgsEl) { msgsEl.scrollTop = msgsEl.scrollHeight; }

  // ── API ──────────────────────────────────────────────────────────────────
  async function apiChat(text, branch) {
    const payload = {
      body: text,
      message_id: `chat-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      context: {
        account_id: account, name: state.name, email: state.email,
        branch: branch, page_url: window.location.href,
        history: state.messages.slice(-10),
      },
    };
    try {
      const r = await fetch('/api/v1/chat/submit', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) return { ok: false };
      const d = await r.json();
      return { ok: true, reply: d.reply || null };
    } catch (_) { return { ok: false }; }
  }

  async function apiCreateInquiry() {
    try {
      const r = await fetch('/api/v1/enterprise/inquiry', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: state.name, email: state.email,
          account_id: Number(account) || null,
          message: 'Chat widget — talk branch',
        }),
      });
      return r.ok || r.status === 201;
    } catch (_) { return false; }
  }

  // ── Phase renderers ──────────────────────────────────────────────────────
  function renderGreeting(body) {
    const p = el('p', { class: 'iq-greeting' });
    p.innerHTML = "Hi there 👋<br>I'm Aria, your InboxIQ guide.<br>What brings you here today?";
    body.appendChild(p);

    [
      { icon: '🎬', label: 'See how it works', phase: 'demo' },
      { icon: '🚀', label: 'Start free trial', fn: () => { window.location.href = signupUrl; } },
      { icon: '💬', label: 'Talk to someone', phase: 'talk_name' },
    ].forEach(({ icon, label, phase, fn }) => {
      const b = el('button', { class: 'iq-cta', on: { click: fn || (() => transition(phase)) } }, [
        el('span', { class: 'iq-icon' }, icon),
        el('span', {}, label),
      ]);
      body.appendChild(b);
    });
  }

  function renderDemo(body) {
    const msgsEl = el('div', { class: 'iq-msgs' });
    msgsEl.appendChild(mkMsg(
      "InboxIQ triages emails automatically so your support team only sees what needs a human. " +
      "I can answer questions about features, pricing, or anything else — what would you like to know?",
      'bot'
    ));
    state.messages.forEach(m => msgsEl.appendChild(mkMsg(m.text, m.role)));
    body.appendChild(msgsEl);

    const { row, inp, btn } = mkInput('Type a message…');
    const send = async () => {
      const text = inp.value.trim(); if (!text) return;
      inp.value = ''; btn.disabled = true;
      state.messages.push({ role: 'user', text });
      msgsEl.appendChild(mkMsg(text, 'user'));
      const t = mkTyping(); msgsEl.appendChild(t); scrollMsgs(msgsEl);
      const result = await apiChat(text, 'demo');
      t.remove(); btn.disabled = false;
      const reply = result.ok ? (result.reply || "Thanks! We'll be in touch.") : "Something went wrong — please try again.";
      msgsEl.appendChild(mkMsg(reply, 'bot'));
      state.messages.push({ role: 'bot', text: reply });
      persist(); scrollMsgs(msgsEl);
      if (!document.getElementById('iq-soft-cta')) {
        const s = el('p', { class: 'iq-soft', id: 'iq-soft-cta' });
        s.innerHTML = `Want to try it yourself? <a href="${signupUrl}">Start free trial →</a>`;
        body.appendChild(s);
      }
    };
    btn.addEventListener('click', send);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
    body.appendChild(row);

    if (state.messages.length >= 2) {
      const s = el('p', { class: 'iq-soft', id: 'iq-soft-cta' });
      s.innerHTML = `Want to try it yourself? <a href="${signupUrl}">Start free trial →</a>`;
      body.appendChild(s);
    }
  }

  function renderTalkName(body) {
    const msgsEl = el('div', { class: 'iq-msgs' });
    msgsEl.appendChild(mkMsg("Happy to connect you with our team! What's your name?", 'bot'));
    body.appendChild(msgsEl);
    const errEl = el('p', { class: 'iq-err' });
    body.appendChild(errEl);
    const { row, inp, btn } = mkInput('Your name');
    const send = () => {
      const name = inp.value.trim();
      if (!name) { errEl.textContent = 'Please enter your name.'; return; }
      state.name = name; persist(); transition('talk_email');
    };
    btn.addEventListener('click', send);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
    body.appendChild(row);
  }

  function renderTalkEmail(body) {
    const msgsEl = el('div', { class: 'iq-msgs' });
    msgsEl.appendChild(mkMsg(`Nice to meet you, ${state.name}! What's the best email to reach you on?`, 'bot'));
    body.appendChild(msgsEl);
    const errEl = el('p', { class: 'iq-err' });
    body.appendChild(errEl);
    const { row, inp, btn } = mkInput('Your email', 'email');
    const send = async () => {
      const email = inp.value.trim().toLowerCase();
      if (!email || !email.includes('@') || !email.split('@')[1]?.includes('.')) {
        errEl.textContent = 'Please enter a valid email address.'; return;
      }
      state.email = email; btn.disabled = true;
      await apiCreateInquiry(); persist();
      transition('talk_chat');
    };
    btn.addEventListener('click', send);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
    body.appendChild(row);
  }

  function renderTalkChat(body) {
    const msgsEl = el('div', { class: 'iq-msgs' });
    const confirm = mkMsg('', 'bot');
    confirm.innerHTML = `Got it! Someone from the team will follow up at <strong>${escapeHtml(state.email)}</strong>. While you wait, is there anything I can help you with now?`;
    msgsEl.appendChild(confirm);
    state.messages.forEach(m => msgsEl.appendChild(mkMsg(m.text, m.role)));
    body.appendChild(msgsEl);

    const { row, inp, btn } = mkInput('Type a message…');
    const send = async () => {
      const text = inp.value.trim(); if (!text) return;
      inp.value = ''; btn.disabled = true;
      state.messages.push({ role: 'user', text });
      msgsEl.appendChild(mkMsg(text, 'user'));
      const t = mkTyping(); msgsEl.appendChild(t); scrollMsgs(msgsEl);
      const result = await apiChat(text, 'talk');
      t.remove(); btn.disabled = false;
      const reply = result.ok ? (result.reply || "Thanks for reaching out!") : "Something went wrong — please try again.";
      msgsEl.appendChild(mkMsg(reply, 'bot'));
      state.messages.push({ role: 'bot', text: reply });
      persist(); scrollMsgs(msgsEl);
    };
    btn.addEventListener('click', send);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
    body.appendChild(row);
  }

  // ── State machine ────────────────────────────────────────────────────────
  const RENDERERS = {
    greeting: renderGreeting,
    demo: renderDemo,
    talk_name: renderTalkName,
    talk_email: renderTalkEmail,
    talk_chat: renderTalkChat,
  };

  function transition(phase) {
    state.phase = phase; persist();
    const panel = document.getElementById('iq-panel');
    panel.innerHTML = ''; panel.classList.add('open');
    document.getElementById('iq-bubble')?.classList.remove('has-badge');
    panel.appendChild(buildHeader(() => {
      state.dismissed = true; state.phase = 'closed'; persist();
      panel.classList.remove('open');
    }));
    const body = el('div', { class: 'iq-body' });
    panel.appendChild(body);
    if (RENDERERS[phase]) RENDERERS[phase](body);
  }

  // ── Init ─────────────────────────────────────────────────────────────────
  function init() {
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    const bubble = el('button', { id: 'iq-bubble', 'aria-label': 'Chat with Aria' });
    bubble.innerHTML = `<img id="iq-bubble-img" src="${AVATAR_URL}" alt="Aria"><div id="iq-badge"></div>`;
    bubble.addEventListener('click', () => {
      const panel = document.getElementById('iq-panel');
      if (panel.classList.contains('open')) {
        panel.classList.remove('open'); state.phase = 'closed'; persist();
      } else {
        transition(state.phase === 'closed' ? 'greeting' : state.phase);
      }
    });
    document.body.appendChild(bubble);
    document.body.appendChild(el('div', { id: 'iq-panel' }));

    // Restore session if visitor had started a flow
    if (!state.dismissed && state.phase !== 'closed') {
      transition(state.phase);
    }

    // Auto-open: badge pulse at 5 s, panel opens at 6.5 s — fresh sessions only
    if (!state.dismissed && state.phase === 'closed') {
      setTimeout(() => {
        if (state.dismissed || state.phase !== 'closed') return;
        document.getElementById('iq-bubble')?.classList.add('has-badge');
        setTimeout(() => {
          if (state.dismissed || state.phase !== 'closed') return;
          transition('greeting');
        }, 1500);
      }, 5000);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
