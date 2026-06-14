(function () {
  'use strict';

  const EMAILS = [
    {
      sender: 'Sarah Chen', initial: 'S', avatarBg: '#EF4444',
      company: 'GrowthOps',
      subject: 'Charged twice this month — need urgent fix',
      preview: "We've been charged twice for our Pro subscription — £58 instead of £29. Finance is flagging it.",
      time: '12:06 AM',
      category: 'Billing', catColor: '#C2410C', catBg: '#FFF7ED',
      urgency: true, intent: 'Billing dispute', sentiment: '😤 Frustrated',
      draft: "Hi Sarah,\n\nThank you for flagging this — I can see the duplicate charge and I'm raising a refund now. You should see £29 back within 3–5 business days.\n\nApologies for the inconvenience.\n\nBest,\nSupport Team",
      unread: true,
    },
    {
      sender: 'Marcus Williams', initial: 'M', avatarBg: '#7C3AED',
      company: 'RetailStack',
      subject: "Can't access my inbox — locked out since 9am",
      preview: "Password reset isn't sending. We have a customer SLA breach if I can't get back in within the hour.",
      time: '11:54 PM',
      category: 'Support', catColor: '#1D4ED8', catBg: '#EFF6FF',
      urgency: true, intent: 'Account access', sentiment: '😤 Frustrated',
      draft: null, unread: true,
    },
    {
      sender: 'Priya Patel', initial: 'P', avatarBg: '#059669',
      company: 'Clara Health',
      subject: 'Interested in InboxIQ for our support team — demo?',
      preview: "We're a 35-person healthtech company using Freshdesk but finding it overkill for our volume.",
      time: 'Apr 25',
      category: 'Demo', catColor: '#065F46', catBg: '#ECFDF5',
      urgency: false, intent: 'Demo request', sentiment: '😊 Positive',
      draft: null, unread: true,
    },
    {
      sender: 'Ana Rodriguez', initial: 'A', avatarBg: '#D97706',
      company: 'Loop Commerce',
      subject: "Automation rule not firing — label isn't applying",
      preview: "Set up a rule to label emails containing 'order' but it's not triggering consistently.",
      time: 'Apr 24',
      category: 'Support', catColor: '#1D4ED8', catBg: '#EFF6FF',
      urgency: false, intent: 'Technical issue', sentiment: '😐 Neutral',
      draft: null, unread: false,
    },
    {
      sender: "James O'Brien", initial: 'J', avatarBg: '#4F46E5',
      company: 'FinServ Advisory',
      subject: 'InboxIQ for shared finance inbox — evaluation',
      preview: "We manage client comms through one shared inbox and spend far too much time triaging manually.",
      time: 'Apr 23',
      category: 'Demo', catColor: '#065F46', catBg: '#ECFDF5',
      urgency: false, intent: 'Demo request', sentiment: '😊 Positive',
      draft: null, unread: false,
    },
    {
      sender: 'Emma Thompson', initial: 'E', avatarBg: '#DB2777',
      company: 'HireBridge',
      subject: 'Feature request — bulk archive after triage',
      preview: "Love the product. One thing that would save us time: a 'bulk archive all triaged low-priority' button.",
      time: 'Apr 22',
      category: 'Feedback', catColor: '#6D28D9', catBg: '#F5F3FF',
      urgency: false, intent: 'Feature request', sentiment: '😊 Positive',
      draft: null, unread: false,
    },
    {
      sender: 'Oliver Mensah', initial: 'O', avatarBg: '#0D9488',
      company: 'Creative Studio',
      subject: 'Just wanted to say — this product is great',
      preview: "Three weeks in and InboxIQ has genuinely changed how our studio handles client emails.",
      time: 'Apr 20',
      category: 'Social', catColor: '#374151', catBg: '#F9FAFB',
      urgency: false, intent: 'Positive feedback', sentiment: '😄 Delighted',
      draft: null, unread: false,
    },
  ];

  const SLOTS = [
    { label: 'Tue Apr 29', time: '10:00 AM' },
    { label: 'Tue Apr 29', time: '2:00 PM' },
    { label: 'Wed Apr 30', time: '10:00 AM' },
    { label: 'Wed Apr 30', time: '3:00 PM' },
  ];
  const BOOKED_SLOT = 2; // Wed Apr 30 · 10:00 AM

  // ── CSS ────────────────────────────────────────────────────────
  const CSS = [
    '#inbox-demo,#inbox-demo *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;padding:0}',
    '#inbox-demo{position:relative;width:100%;background:#fff;overflow:hidden;user-select:none;border-radius:inherit}',

    '.id-chrome{background:#3a3a3a;padding:8px 12px 0;display:flex;align-items:center;gap:8px;border-radius:inherit;border-bottom-left-radius:0;border-bottom-right-radius:0}',
    '.id-dots{display:flex;gap:5px;padding-bottom:8px}',
    '.id-dot{width:11px;height:11px;border-radius:50%}',
    '.id-tab{background:#fff;border-radius:8px 8px 0 0;padding:5px 12px;font-size:11px;color:#333;display:flex;align-items:center;gap:5px;max-width:230px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-left:4px}',
    '.id-urlbar{flex:1;background:#525252;border-radius:5px;padding:4px 10px;font-size:10px;color:#bbb;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-left:6px;margin-bottom:8px}',

    '.id-body{display:flex;height:500px;overflow:hidden}',

    '.id-sidebar{width:172px;flex-shrink:0;background:#f6f8fc;border-right:1px solid #e0e0e0;display:flex;flex-direction:column;padding:6px 0;overflow:hidden}',
    '.id-compose{margin:2px 10px 10px;background:#c2e7ff;border-radius:16px;padding:7px 14px;font-size:12px;font-weight:700;color:#001d35;display:flex;align-items:center;gap:7px;flex-shrink:0}',
    '.id-nav{padding:4px 8px 4px 14px;font-size:12px;color:#444;display:flex;align-items:center;gap:7px;border-radius:0 20px 20px 0;flex-shrink:0}',
    '.id-nav.on{background:#d3e3fd;font-weight:700;color:#001d35}',
    '.id-nav-n{margin-left:auto;font-size:11px;font-weight:700;color:#001d35}',
    '.id-lhead{padding:8px 14px 3px;font-size:10px;font-weight:700;color:#666;letter-spacing:.06em;text-transform:uppercase;flex-shrink:0}',
    '.id-lrow{padding:3px 10px 3px 14px;font-size:11px;color:#444;display:flex;align-items:center;gap:6px;flex-shrink:0}',
    '.id-ldot{width:8px;height:8px;border-radius:50%;flex-shrink:0}',

    '.id-main{flex:1;min-width:0;display:flex;flex-direction:column;position:relative;overflow:hidden}',
    '.id-topbar{padding:7px 10px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #e0e0e0;flex-shrink:0}',
    '.id-search{flex:1;background:#eaf1fb;border-radius:20px;padding:5px 14px;font-size:12px;color:#666;display:flex;align-items:center;gap:6px}',
    '.id-uavatar{width:28px;height:28px;border-radius:50%;background:#5B5BD6;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0}',

    '.id-status{background:#5B5BD6;color:#fff;font-size:11px;padding:0 14px;display:flex;align-items:center;gap:7px;flex-shrink:0;height:0;overflow:hidden;transition:height .3s,padding .3s}',
    '.id-status.on{height:28px;padding:5px 14px}',
    '.id-spin{width:11px;height:11px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:id-spin .7s linear infinite;flex-shrink:0}',
    '@keyframes id-spin{to{transform:rotate(360deg)}}',

    '.id-list{flex:1;overflow:hidden}',
    '.id-row{display:flex;align-items:center;gap:9px;padding:5px 12px;border-bottom:1px solid #f1f3f4;transition:background .2s}',
    '.id-row.unread{background:#fff}',
    '.id-row.read{background:#f6f8fc}',
    '.id-row.lit{background:#e8f0fe}',
    '.id-ava{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0}',
    '.id-rcol{flex:1;min-width:0}',
    '.id-rtop{display:flex;align-items:center;gap:5px;margin-bottom:1px}',
    '.id-rname{font-size:12px;font-weight:700;color:#202124;white-space:nowrap}',
    '.id-row.read .id-rname{font-weight:400;color:#5f6368}',
    '.id-rsubj{font-size:11.5px;color:#202124;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.id-row.read .id-rsubj{color:#5f6368}',
    '.id-rprev{font-size:11px;color:#5f6368;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.id-rmeta{flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:3px}',
    '.id-rtime{font-size:11px;color:#5f6368;white-space:nowrap}',
    '.id-row.unread .id-rtime{font-weight:700;color:#202124}',

    '.id-cat{display:inline-flex;align-items:center;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;opacity:0;transform:scale(.6);transition:opacity .25s,transform .25s}',
    '.id-cat.on{opacity:1;transform:scale(1)}',
    '.id-urg{display:inline-flex;align-items:center;padding:1px 6px;border-radius:10px;font-size:10px;font-weight:700;background:#FEE2E2;color:#DC2626;opacity:0;transition:opacity .3s;white-space:nowrap}',
    '.id-urg.on{opacity:1}',

    /* email view */
    '.id-view{position:absolute;inset:0;background:#fff;display:flex;flex-direction:column;transform:translateX(105%);transition:transform .38s cubic-bezier(.4,0,.2,1);overflow:hidden}',
    '.id-view.open{transform:translateX(0)}',
    '.id-vhead{padding:10px 14px;border-bottom:1px solid #e0e0e0;flex-shrink:0}',
    '.id-vsubj{font-size:14px;font-weight:700;color:#202124;margin-bottom:6px;line-height:1.3}',
    '.id-vfrom{display:flex;align-items:center;gap:9px}',
    '.id-vava{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff;flex-shrink:0}',
    '.id-vname{font-size:12px;font-weight:700;color:#202124}',
    '.id-vaddr{font-size:11px;color:#5f6368}',
    '.id-vbody{padding:9px 14px;font-size:12px;color:#202124;line-height:1.65;flex-shrink:0}',

    /* AI panel */
    '.id-aipanel{margin:5px 14px;background:#F8F7FF;border:1px solid #DDD6FE;border-radius:10px;padding:8px 12px;flex-shrink:0}',
    '.id-aititle{font-size:11px;font-weight:700;color:#5B5BD6;margin-bottom:5px;display:flex;align-items:center;gap:5px}',
    '.id-chips{display:flex;gap:5px;flex-wrap:wrap}',
    '.id-chip{padding:2px 8px;border-radius:8px;font-size:10px;font-weight:700}',

    /* draft panel */
    '.id-draft{margin:5px 14px;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;flex:1;display:flex;flex-direction:column;min-height:0}',
    '.id-dhead{background:#f6f8fc;padding:5px 12px;font-size:11px;font-weight:700;color:#5B5BD6;display:flex;align-items:center;gap:5px;flex-shrink:0}',
    '.id-dbody{padding:9px 12px;font-size:12px;color:#202124;line-height:1.65;flex:1;overflow:hidden;white-space:pre-wrap}',
    '.id-cursor{display:inline-block;width:2px;height:13px;background:#5B5BD6;animation:id-blink 1s step-end infinite;vertical-align:text-bottom}',
    '@keyframes id-blink{50%{opacity:0}}',
    '.id-dfoot{padding:6px 12px;background:#f6f8fc;display:flex;gap:7px;flex-shrink:0}',
    '.id-btn-p{background:#5B5BD6;color:#fff;border:none;border-radius:14px;padding:5px 13px;font-size:11px;font-weight:700;cursor:default}',
    '.id-btn-s{background:transparent;color:#5B5BD6;border:1px solid #C4B5FD;border-radius:14px;padding:5px 13px;font-size:11px;font-weight:700;cursor:default}',

    /* booking panel */
    '.id-bkpanel{margin:5px 14px;border:1px solid #DDD6FE;border-radius:10px;overflow:hidden;flex:1;display:flex;flex-direction:column;min-height:0}',
    '.id-bkhead{background:#F8F7FF;padding:6px 12px;font-size:11px;font-weight:700;color:#5B5BD6;display:flex;align-items:center;gap:5px;flex-shrink:0}',
    '.id-bkdetect{padding:7px 12px;font-size:11px;color:#5f6368;border-bottom:1px solid #ede9fe;flex-shrink:0}',
    '.id-slots{padding:6px 12px;display:grid;grid-template-columns:1fr 1fr;gap:6px;flex-shrink:0}',
    '.id-slot{padding:7px 8px;border:1px solid #e8eaed;border-radius:8px;color:#202124;display:flex;flex-direction:column;align-items:center;gap:2px;transition:all .25s;cursor:default;text-align:center}',
    '.id-slot.on{background:#5B5BD6;color:#fff;border-color:#5B5BD6;font-weight:700}',
    '.id-slot-date{font-size:10px;color:#5f6368}',
    '.id-slot.on .id-slot-date{color:rgba(255,255,255,.75)}',
    '.id-slot-time{font-size:12px;font-weight:700}',
    '.id-bkinputs{padding:0 12px 6px;display:flex;flex-direction:column;gap:5px;flex-shrink:0}',
    '.id-bkinput{border:1px solid #e0e0e0;border-radius:6px;padding:6px 10px;font-size:11px;color:#5f6368;background:#fff}',
    '.id-bkfoot{padding:0 12px 8px;flex-shrink:0}',
    '.id-bkbtn{background:#5B5BD6;color:#fff;border:none;border-radius:8px;padding:9px;font-size:12px;font-weight:700;cursor:default;width:100%;display:block;text-align:center}',

    /* booking confirm */
    '.id-bkconfirm{margin:5px 14px;background:#ECFDF5;border:1px solid #6EE7B7;border-radius:10px;padding:9px 12px;font-size:11px;color:#065F46;display:flex;align-items:flex-start;gap:8px;opacity:0;transform:translateY(6px);transition:opacity .35s,transform .35s;flex-shrink:0}',
    '.id-bkconfirm.on{opacity:1;transform:translateY(0)}',
    '.id-bkchk{font-size:16px;flex-shrink:0;line-height:1.2}',

    /* booking link */
    '.id-bklink{display:inline-block;color:#5B5BD6;text-decoration:underline;font-weight:600;cursor:default;padding:2px 6px;border-radius:4px;transition:background .2s,color .15s,transform .15s}',
    '.id-bklink.hover{background:#EDE9FE}',
    '.id-bklink.clicked{background:#5B5BD6;color:#fff;transform:scale(.96);transition:background .08s,color .08s,transform .08s}',
  ].join('');

  // ── SVG helpers ────────────────────────────────────────────────
  const mksvg = function(path, size, fill) {
    return '<svg width="' + (size||13) + '" height="' + (size||13) + '" viewBox="0 0 24 24" fill="' + (fill||'currentColor') + '">' + path + '</svg>';
  };
  const P = {
    pencil: '<path d="M20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83zM3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z"/>',
    layers: '<path d="M11.99 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>',
    search: '<path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>',
    cal:    '<path d="M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z"/>',
    inbox:  '<path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z"/>',
    star:   '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>',
  };

  // ── Build DOM ──────────────────────────────────────────────────
  const container = document.getElementById('inbox-demo');
  if (!container) return;

  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  container.innerHTML =
    '<div class="id-chrome">' +
      '<div class="id-dots">' +
        '<div class="id-dot" style="background:#ff5f57"></div>' +
        '<div class="id-dot" style="background:#febc2e"></div>' +
        '<div class="id-dot" style="background:#28c840"></div>' +
      '</div>' +
      '<div class="id-tab">' +
        '<svg width="12" height="12" viewBox="0 0 24 24"><path fill="#EA4335" d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z"/></svg>' +
        'Inbox (10) &middot; InboxIQ reviewer' +
      '</div>' +
      '<div class="id-urlbar">mail.google.com/mail/u/0/#inbox</div>' +
    '</div>' +
    '<div class="id-body">' +
      '<div class="id-sidebar">' +
        '<div class="id-compose">' + mksvg(P.pencil, 13, '#001d35') + ' Compose</div>' +
        '<div class="id-nav on">' + mksvg(P.inbox, 13, '#001d35') + 'Inbox<span class="id-nav-n">10</span></div>' +
        '<div class="id-nav">' + mksvg(P.star, 13, '#666') + 'Starred</div>' +
        '<div class="id-nav">' + mksvg('<path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z"/>', 13, '#666') + 'Sent</div>' +
        '<div class="id-nav">' + mksvg('<path d="M20.54 5.23l-1.39-1.68C18.88 3.21 18.47 3 18 3H6c-.47 0-.88.21-1.16.55L3.46 5.23C3.17 5.57 3 6.02 3 6.5V19c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6.5c0-.48-.17-.93-.46-1.27zM12 17.5 6.5 12H10v-2h4v2h3.5L12 17.5zM5.12 5l.81-1h12l.94 1H5.12z"/>', 13, '#666') + 'Drafts<span class="id-nav-n">4</span></div>' +
        '<div class="id-lhead">Labels</div>' +
        '<div class="id-lrow"><div class="id-ldot" style="background:#F97316"></div>InboxIQ/Billing</div>' +
        '<div class="id-lrow"><div class="id-ldot" style="background:#DC2626"></div>Urgent</div>' +
        '<div class="id-lrow"><div class="id-ldot" style="background:#2563EB"></div>InboxIQ/Support</div>' +
        '<div class="id-lrow"><div class="id-ldot" style="background:#059669"></div>InboxIQ/Demo</div>' +
        '<div class="id-lrow"><div class="id-ldot" style="background:#7C3AED"></div>InboxIQ/Feedback</div>' +
        '<div class="id-lrow"><div class="id-ldot" style="background:#6B7280"></div>InboxIQ/Social</div>' +
      '</div>' +
      '<div class="id-main">' +
        '<div class="id-topbar">' +
          '<div class="id-search">' + mksvg(P.search, 13, '#666') + 'Search mail</div>' +
          '<div class="id-uavatar">K</div>' +
        '</div>' +
        '<div class="id-status" id="id-status"><div class="id-spin"></div><span id="id-stxt">InboxIQ is triaging your inbox&hellip;</span></div>' +
        '<div class="id-list" id="id-list"></div>' +
        '<div class="id-view" id="id-view"></div>' +
      '</div>' +
    '</div>';

  // ── Rows ───────────────────────────────────────────────────────
  const list = document.getElementById('id-list');
  EMAILS.forEach(function (e, i) {
    const row = document.createElement('div');
    row.className = 'id-row ' + (e.unread ? 'unread' : 'read');
    row.id = 'id-row-' + i;
    row.innerHTML =
      '<div class="id-ava" style="background:' + e.avatarBg + '">' + e.initial + '</div>' +
      '<div class="id-rcol">' +
        '<div class="id-rtop">' +
          '<span class="id-rname">' + e.sender + '</span>' +
          '<span class="id-cat" id="id-cat-' + i + '" style="background:' + e.catBg + ';color:' + e.catColor + '">' + e.category + '</span>' +
        '</div>' +
        '<div class="id-rsubj">' + e.subject + '</div>' +
        '<div class="id-rprev">' + e.preview + '</div>' +
      '</div>' +
      '<div class="id-rmeta">' +
        '<div class="id-rtime">' + e.time + '</div>' +
        (e.urgency ? '<div class="id-urg" id="id-urg-' + i + '">⚡ Urgent</div>' : '') +
      '</div>';
    list.appendChild(row);
  });

  // ── Helpers ────────────────────────────────────────────────────
  let timers = [];
  const at = function(fn, ms) { timers.push(setTimeout(fn, ms)); };
  const q = function(id) { return document.getElementById(id); };

  const resetAll = function() {
    timers.forEach(clearTimeout); timers = [];
    EMAILS.forEach(function (_, i) {
      const c = q('id-cat-' + i); if (c) c.classList.remove('on');
      const u = q('id-urg-' + i); if (u) u.classList.remove('on');
      const r = q('id-row-' + i); if (r) r.classList.remove('lit');
    });
    const s = q('id-status');
    if (s) { s.classList.remove('on'); s.style.background = '#5B5BD6'; }
    const v = q('id-view');
    if (v) { v.classList.remove('open'); v.innerHTML = ''; }
  };

  // ── Scene 1: Triage + draft ────────────────────────────────────
  const scene1 = function(done) {
    const STAGGER = 400, labelsStart = 1000;
    const labelsEnd = labelsStart + EMAILS.length * STAGGER;

    at(function () { const s = q('id-status'); if (s) s.classList.add('on'); }, 600);

    EMAILS.forEach(function (_, i) {
      at(function () {
        const c = q('id-cat-' + i); if (c) c.classList.add('on');
      }, labelsStart + i * STAGGER);
    });

    at(function () { const u = q('id-urg-0'); if (u) u.classList.add('on'); }, labelsEnd + 150);
    at(function () { const u = q('id-urg-1'); if (u) u.classList.add('on'); }, labelsEnd + 350);

    at(function () {
      const s = q('id-status'), t = q('id-stxt');
      if (s) s.style.background = '#059669';
      if (t) t.textContent = '✓ Triage complete — 2 urgent · 3 normal · 2 low priority';
    }, labelsEnd + 600);

    const openAt = labelsEnd + 1800;
    at(function () { openDraftEmail(0); }, openAt);
    at(function () { typeDraft(EMAILS[0].draft); }, openAt + 500);

    const closeAt = openAt + 7200;
    at(function () {
      const v = q('id-view'); if (v) v.classList.remove('open');
      const r = q('id-row-0'); if (r) r.classList.remove('lit');
      const s = q('id-status'), t = q('id-stxt');
      if (s) { s.style.background = '#5B5BD6'; }
      if (t) t.textContent = 'InboxIQ is triaging your inbox…';
    }, closeAt);

    at(done, closeAt + 800);
  };

  const openDraftEmail = function(idx) {
    const e = EMAILS[idx];
    const r = q('id-row-' + idx); if (r) r.classList.add('lit');
    const v = q('id-view'); if (!v) return;
    const addr = e.sender.toLowerCase().replace(/'/g, '').replace(' ', '.') + '@' + e.company.toLowerCase().replace(' ', '') + '.com';

    v.innerHTML =
      '<div class="id-vhead">' +
        '<div class="id-vsubj">' + e.subject + '</div>' +
        '<div class="id-vfrom">' +
          '<div class="id-vava" style="background:' + e.avatarBg + '">' + e.initial + '</div>' +
          '<div>' +
            '<div class="id-vname">' + e.sender + ' <span style="font-weight:400;color:#5f6368;font-size:11px">&lt;' + addr + '&gt;</span></div>' +
            '<div class="id-vaddr">to support@acmedemo.com &middot; ' + e.time + '</div>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="id-vbody">' + e.preview + ' This is critical for our finance team. Please resolve today.</div>' +
      '<div class="id-aipanel">' +
        '<div class="id-aititle">' + mksvg(P.layers, 11, '#5B5BD6') + ' InboxIQ Triage</div>' +
        '<div class="id-chips">' +
          '<span class="id-chip" style="background:#FEE2E2;color:#DC2626">⚡ Urgent</span>' +
          '<span class="id-chip" style="background:' + e.catBg + ';color:' + e.catColor + '">' + e.intent + '</span>' +
          '<span class="id-chip" style="background:#fef9c3;color:#92400e">' + e.sentiment + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="id-draft">' +
        '<div class="id-dhead">' + mksvg(P.pencil, 11, '#5B5BD6') + ' AI Draft Reply</div>' +
        '<div class="id-dbody" id="id-dbody"><span class="id-cursor"></span></div>' +
        '<div class="id-dfoot"><button class="id-btn-p">Approve &amp; Send</button><button class="id-btn-s">Edit</button></div>' +
      '</div>';

    v.classList.add('open');
  };

  const typeDraft = function(text) {
    const el = q('id-dbody'); if (!el) return;
    const cursor = el.querySelector('.id-cursor');
    let i = 0;
    const iv = setInterval(function () {
      if (!q('id-dbody') || i >= text.length) { clearInterval(iv); return; }
      el.insertBefore(document.createTextNode(text[i]), cursor);
      i++;
    }, 18);
    timers.push(iv);
  };

  // ── Scene 2: Booking ───────────────────────────────────────────
  const scene2 = function(done) {
    const e = EMAILS[2]; // Priya Patel — demo request
    const addr = 'priya.patel@clarahealth.com';

    // Highlight the demo request row
    at(function () {
      const r = q('id-row-2'); if (r) r.classList.add('lit');
      const s = q('id-status'), t = q('id-stxt');
      if (s) { s.classList.add('on'); s.style.background = '#5B5BD6'; }
      if (t) t.textContent = 'InboxIQ detected a meeting request in this email';
    }, 400);

    // Open email — body shows the auto-generated booking link, panel hidden
    at(function () {
      const v = q('id-view'); if (!v) return;

      const slotsHtml = SLOTS.map(function (s, i) {
        return '<div class="id-slot" id="id-slot-' + i + '"><span class="id-slot-date">' + s.label + '</span><span class="id-slot-time">' + s.time + '</span></div>';
      }).join('');

      v.innerHTML =
        '<div class="id-vhead">' +
          '<div class="id-vsubj">' + e.subject + '</div>' +
          '<div class="id-vfrom">' +
            '<div class="id-vava" style="background:' + e.avatarBg + '">' + e.initial + '</div>' +
            '<div>' +
              '<div class="id-vname">' + e.sender + ' <span style="font-weight:400;color:#5f6368;font-size:11px">&lt;' + addr + '&gt;</span></div>' +
              '<div class="id-vaddr">to support@acmedemo.com &middot; ' + e.time + '</div>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="id-vbody">We\'re a 35-person healthtech company using Freshdesk — finding it overkill for our volume. Would love a quick demo.<br><br>' +
          '<span class="id-bklink" id="id-bklink">&#x1F4C5; Book a 30-min call &rarr; kalevent.com/book/support</span>' +
        '</div>' +
        '<div class="id-aipanel">' +
          '<div class="id-aititle">' + mksvg(P.layers, 11, '#5B5BD6') + ' InboxIQ Triage</div>' +
          '<div class="id-chips">' +
            '<span class="id-chip" style="background:#ECFDF5;color:#065F46">&#x1F4C5; Meeting request</span>' +
            '<span class="id-chip" style="background:' + e.catBg + ';color:' + e.catColor + '">' + e.intent + '</span>' +
            '<span class="id-chip" style="background:#EFF6FF;color:#1D4ED8">' + e.sentiment + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="id-bkpanel" id="id-bkpanel" style="opacity:0;transform:translateY(8px);transition:opacity .4s,transform .4s">' +
          '<div class="id-bkhead">' + mksvg(P.cal, 11, '#5B5BD6') + ' Book a meeting with Support</div>' +
          '<div class="id-bkdetect">30-minute call &middot; Video link sent on confirmation</div>' +
          '<div class="id-slots">' + slotsHtml + '</div>' +
          '<div class="id-bkinputs">' +
            '<div class="id-bkinput">Priya Patel</div>' +
            '<div class="id-bkinput">priya.patel@clarahealth.com</div>' +
          '</div>' +
          '<div class="id-bkfoot"><div class="id-bkbtn">Confirm booking</div></div>' +
        '</div>';

      v.classList.add('open');
    }, 900);

    // Status: booking link detected
    at(function () {
      const t = q('id-stxt');
      if (t) t.textContent = 'Auto-booking link detected — click to open scheduler';
    }, 2000);

    // Hover over the booking link
    at(function () {
      const lk = q('id-bklink'); if (lk) lk.classList.add('hover');
    }, 2300);

    // Click the booking link
    at(function () {
      const lk = q('id-bklink');
      if (lk) { lk.classList.remove('hover'); lk.classList.add('clicked'); }
    }, 2800);

    // Booking panel slides in
    at(function () {
      const bp = q('id-bkpanel');
      if (bp) { bp.style.opacity = '1'; bp.style.transform = 'translateY(0)'; }
      const t = q('id-stxt');
      if (t) t.textContent = 'Opening booking page…';
    }, 3200);

    // Highlight chosen slot
    at(function () {
      const sl = q('id-slot-' + BOOKED_SLOT); if (sl) sl.classList.add('on');
    }, 5100);

    // Swap booking panel to confirmation success state
    at(function () {
      const bp = q('id-bkpanel');
      if (bp) {
        bp.style.background = '#ECFDF5';
        bp.style.borderColor = '#6EE7B7';
        bp.innerHTML =
          '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:8px;padding:24px;text-align:center">' +
            '<div style="width:40px;height:40px;background:#059669;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:20px;line-height:1">&#x2713;</div>' +
            '<div style="font-size:13px;font-weight:700;color:#065F46">Meeting booked</div>' +
            '<div style="font-size:11px;color:#065F46;font-weight:600">Wed Apr 30 at 10:00 AM</div>' +
            '<div style="font-size:11px;color:#6B7280">Invite sent to priya.patel@clarahealth.com</div>' +
          '</div>';
      }
      const s = q('id-status'), t = q('id-stxt');
      if (s) s.style.background = '#059669';
      if (t) t.textContent = '✓ Booking confirmed · calendar invite dispatched';
    }, 6700);

    // Close
    at(function () {
      const v = q('id-view'); if (v) v.classList.remove('open');
      const r = q('id-row-2'); if (r) r.classList.remove('lit');
      const s = q('id-status'); if (s) s.classList.remove('on');
    }, 9200);

    at(done, 10000);
  };

  // ── Main loop ──────────────────────────────────────────────────
  const run = function() {
    resetAll();
    scene1(function () {
      scene2(function () {
        at(run, 600);
      });
    });
  };

  run();

})();
