(() => {
  const sendBtn = document.getElementById('sendTestEmailBtn');
  const statusEl = document.getElementById('testEmailStatus');
  const emailInput = document.getElementById('testEmailInput');
  const triageResults = document.getElementById('triageResults');
  const triageList = document.getElementById('triageList');
  const connectGmailBtn = document.getElementById('connectGmailBtn');
  const connectOutlookBtn = document.getElementById('connectOutlookBtn');
  const connectStatus = document.getElementById('connectStatus');
  const connectSourcesStatus = document.getElementById('connectSourcesStatus');
  const sourceConnectBtns = Array.from(document.querySelectorAll('.source-connect-btn'));
  const sourceTestBtns = Array.from(document.querySelectorAll('.source-test-btn'));
  const formsConnectBtn = document.getElementById('formsConnectBtn');
  const formsCopyBtns = Array.from(document.querySelectorAll('.copy-forms-url'));
  const formsConnectModal = document.getElementById('formsConnectModal');
  const closeFormsModalBtn = document.getElementById('closeFormsModal');
  const formsModalBackdrop = document.getElementById('formsModalBackdrop');
  const formsIntakeUrlModal = document.getElementById('formsIntakeUrlModal');
  const formsShimUrlModal = document.getElementById('formsShimUrlModal');
  const formsPayloadSampleModal = document.getElementById('formsPayloadSampleModal');
  const markFormsConnectedModal = document.getElementById('markFormsConnectedModal');
  const formsConnectStatusModal = document.getElementById('formsConnectStatusModal');
  let formsConnectTriggerBtn = null;
  const twilioConnectModal = document.getElementById('twilioConnectModal');
  const closeTwilioModalBtn = document.getElementById('closeTwilioModal');
  const cancelTwilioModalBtn = document.getElementById('cancelTwilioModal');
  const twilioModalBackdrop = document.getElementById('twilioModalBackdrop');
  const twilioConnectionForm = document.getElementById('twilioConnectionForm');
  const twilioConnectStatus = document.getElementById('twilioConnectStatus');
  let twilioConnectTriggerBtn = null;
  const socialConnectModal = document.getElementById('socialConnectModal');
  const closeSocialModalBtn = document.getElementById('closeSocialModal');
  const cancelSocialModalBtn = document.getElementById('cancelSocialModal');
  const socialModalBackdrop = document.getElementById('socialModalBackdrop');
  const socialConnectionForm = document.getElementById('socialConnectionForm');
  const socialConnectStatus = document.getElementById('socialConnectStatus');
  let socialConnectTriggerBtn = null;
  const chatConnectModal = document.getElementById('chatConnectModal');
  const closeChatModalBtn = document.getElementById('closeChatModal');
  const cancelChatModalBtn = document.getElementById('cancelChatModal');
  const chatModalBackdrop = document.getElementById('chatModalBackdrop');
  const chatConnectionForm = document.getElementById('chatConnectionForm');
  const chatConnectStatus = document.getElementById('chatConnectStatus');
  let chatConnectTriggerBtn = null;
  const rawConnectionId = connectStatus?.dataset?.connectionId;
  const normalizedConnectionId = (rawConnectionId || '').trim();
  const hasConnectionId = normalizedConnectionId && !['none', 'null', 'undefined'].includes(normalizedConnectionId.toLowerCase());
  const getConnectionId = () => (hasConnectionId ? normalizedConnectionId : '');
  const pollNowBtn = document.getElementById('pollNowBtn');
  const pollStatus = document.getElementById('pollStatus');
  const lastPollLine = document.getElementById('lastPollLine');
  let lastKnownPollAt = null;
  let autoPollAttempted = false;
  const dashboardTabs = Array.from(document.querySelectorAll('[data-dashboard-section]'));
  const dashboardPanels = Array.from(document.querySelectorAll('[data-dashboard-section-panel]'));
  const feedbackTabs = Array.from(document.querySelectorAll('[data-feedback-section]'));
  const feedbackPanels = Array.from(document.querySelectorAll('[data-feedback-panel]'));

  const getCookie = (name) => {
    return document.cookie
      .split(';')
      .map((c) => c.trim())
      .find((c) => c.startsWith(name + '='))?.split('=')[1];
  };

  function setStatus(type, message) {
    if (!statusEl) return;
    const map = {
      success: 'border-emerald-400/50 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/50 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/50 bg-indigo-500/10 text-indigo-100',
    };
    statusEl.className = `mt-3 text-xs rounded-xl border px-3 py-2 ${map[type] || map.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  }

  function setConnectSourcesStatus(type, message) {
    if (!connectSourcesStatus) return;
    const map = {
      success: 'text-emerald-300',
      error: 'text-rose-300',
      info: 'text-indigo-300',
    };
    connectSourcesStatus.className = `mt-2 text-xs ${map[type] || map.info}`;
    connectSourcesStatus.textContent = message;
    connectSourcesStatus.classList.remove('hidden');
  }

  function openFormsModal(triggerBtn) {
    if (!formsConnectModal) return;
    formsConnectTriggerBtn = triggerBtn || null;
    formsConnectStatusModal && (formsConnectStatusModal.textContent = '');

    // Close user menu if open
    const userMenu = document.getElementById('userMenu');
    if (userMenu && !userMenu.classList.contains('hidden')) {
      userMenu.classList.add('hidden');
    }

    // Hide main content and header to prevent decorative elements from overlaying
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) {
      mainEl.style.visibility = 'hidden';
    }
    if (headerEl) {
      headerEl.style.visibility = 'hidden';
    }

    formsConnectModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeFormsModal() {
    if (!formsConnectModal) return;
    formsConnectModal.classList.add('hidden');
    document.body.style.overflow = '';

    // Restore main content and header visibility
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) {
      mainEl.style.visibility = '';
    }
    if (headerEl) {
      headerEl.style.visibility = '';
    }
  }

  function openTwilioModal(triggerBtn) {
    if (!twilioConnectModal) return;
    twilioConnectTriggerBtn = triggerBtn || null;
    if (twilioConnectStatus) twilioConnectStatus.textContent = '';

    // Close user menu if open
    const userMenu = document.getElementById('userMenu');
    if (userMenu && !userMenu.classList.contains('hidden')) {
      userMenu.classList.add('hidden');
    }

    // Hide main content and header to prevent decorative elements from overlaying
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) {
      mainEl.style.visibility = 'hidden';
    }
    if (headerEl) {
      headerEl.style.visibility = 'hidden';
    }

    twilioConnectModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeTwilioModal() {
    if (!twilioConnectModal) return;
    twilioConnectModal.classList.add('hidden');
    document.body.style.overflow = '';

    // Restore main content and header visibility
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) {
      mainEl.style.visibility = '';
    }
    if (headerEl) {
      headerEl.style.visibility = '';
    }

    // Reset form
    if (twilioConnectionForm) {
      twilioConnectionForm.reset();
    }
    if (twilioConnectStatus) {
      twilioConnectStatus.classList.add('hidden');
    }
  }

  function setTwilioStatus(type, message) {
    if (!twilioConnectStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    twilioConnectStatus.className = `text-xs px-4 py-3 rounded-xl border ${map[type] || map.info}`;
    twilioConnectStatus.textContent = message;
    twilioConnectStatus.classList.remove('hidden');
  }

  async function handleTwilioSubmit(event) {
    event.preventDefault();

    const formData = new FormData(twilioConnectionForm);
    formData.append('action', 'save_voice');

    const submitBtn = document.getElementById('saveTwilioBtn');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Saving...';
    }

    setTwilioStatus('info', 'Saving Twilio configuration...');

    try {
      const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
      const response = await fetch('/integrations/webhooks', {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
        body: formData,
      });

      if (response.ok) {
        setTwilioStatus('success', '✅ Twilio connected successfully! Your voice/IVR integration is now active.');

        // Mark voice channel as connected
        await handleSourceConnect('voice', twilioConnectTriggerBtn);

        setTimeout(() => {
          closeTwilioModal();
          setConnectSourcesStatus('success', 'Voice/IVR connected via Twilio');
        }, 2000);
      } else {
        const data = await response.json().catch(() => ({}));
        setTwilioStatus('error', data.error || data.message || 'Failed to save Twilio configuration');
      }
    } catch (err) {
      setTwilioStatus('error', err.message || 'Network error. Please try again.');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save & Connect';
      }
    }
  }

  function openSocialModal(triggerBtn) {
    if (!socialConnectModal) return;
    socialConnectTriggerBtn = triggerBtn || null;
    if (socialConnectStatus) socialConnectStatus.textContent = '';

    // Close user menu if open
    const userMenu = document.getElementById('userMenu');
    if (userMenu && !userMenu.classList.contains('hidden')) {
      userMenu.classList.add('hidden');
    }

    // Hide main content and header
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) mainEl.style.visibility = 'hidden';
    if (headerEl) headerEl.style.visibility = 'hidden';

    socialConnectModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeSocialModal() {
    if (!socialConnectModal) return;
    socialConnectModal.classList.add('hidden');
    document.body.style.overflow = '';

    // Restore visibility
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) mainEl.style.visibility = '';
    if (headerEl) headerEl.style.visibility = '';

    // Reset form
    if (socialConnectionForm) socialConnectionForm.reset();
    if (socialConnectStatus) socialConnectStatus.classList.add('hidden');

    // Reset to default view
    updateSocialLabels('whatsapp', 'meta_cloud_api');
  }

  function setSocialStatus(type, message) {
    if (!socialConnectStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    socialConnectStatus.className = `text-xs px-4 py-3 rounded-xl border ${map[type] || map.info}`;
    socialConnectStatus.textContent = message;
    socialConnectStatus.classList.remove('hidden');
  }

  function updateSocialLabels(platform, gateway) {
    const apiKeyLabel = document.getElementById('socialApiKeyLabel');
    const apiSecretLabel = document.getElementById('socialApiSecretLabel');
    const apiKeyHelp = document.getElementById('socialApiKeyHelp');
    const identifierLabel = document.getElementById('socialIdentifierLabel');
    const identifierHelp = document.getElementById('socialIdentifierHelp');
    const identifierSection = document.getElementById('socialIdentifierSection');
    const gatewaySection = document.getElementById('whatsappGatewaySection');
    const webhookInstructions = document.getElementById('socialWebhookInstructions');
    const setupTitle = document.getElementById('socialSetupTitle');
    const setupDesc = document.getElementById('socialSetupDesc');

    const config = {
      whatsapp: {
        apiKey: 'API Key / App ID',
        apiSecret: 'API Secret / Access Token',
        apiKeyHelp: 'Find this in your WhatsApp Business API settings.',
        identifier: 'WhatsApp Phone Number',
        identifierHelp: 'Your WhatsApp Business phone number (e.g., +1234567890).',
        showIdentifier: true,
        showGateway: true,
        showWebhook: true,
        setupTitle: 'WhatsApp Webhook Setup',
        setupDesc: 'Configure your WhatsApp webhook to send messages to:',
      },
      facebook: {
        apiKey: 'Facebook App ID',
        apiSecret: 'Page Access Token',
        apiKeyHelp: 'Find this in Facebook Developer Console → Your App → Settings.',
        identifier: 'Facebook Page ID',
        identifierHelp: 'Your Facebook Page ID (numeric).',
        showIdentifier: true,
        showGateway: false,
        showWebhook: true,
        setupTitle: 'Facebook Messenger Webhook',
        setupDesc: 'Configure webhook in Facebook App → Messenger → Settings:',
      },
      instagram: {
        apiKey: 'Instagram Business Account ID',
        apiSecret: 'Access Token',
        apiKeyHelp: 'Find this in Facebook Developer Console → Instagram Settings.',
        identifier: 'Instagram Username',
        identifierHelp: 'Your Instagram Business account username.',
        showIdentifier: true,
        showGateway: false,
        showWebhook: true,
        setupTitle: 'Instagram Webhook Setup',
        setupDesc: 'Configure webhook in Facebook App → Instagram → Settings:',
      },
      twitter: {
        apiKey: 'Twitter API Key',
        apiSecret: 'API Secret Key',
        apiKeyHelp: 'Find this in Twitter Developer Portal → Your App → Keys.',
        identifier: 'Twitter Account ID',
        identifierHelp: 'Your Twitter account ID (numeric).',
        showIdentifier: true,
        showGateway: false,
        showWebhook: true,
        setupTitle: 'Twitter Webhook Setup',
        setupDesc: 'Register webhook URL in Twitter Developer Portal:',
      },
      other: {
        apiKey: 'API Key / Client ID',
        apiSecret: 'API Secret / Token',
        apiKeyHelp: 'Enter your platform\'s API credentials.',
        identifier: 'Account Identifier',
        identifierHelp: 'Your account ID, phone number, or username.',
        showIdentifier: true,
        showGateway: false,
        showWebhook: false,
      },
    };

    const platformConfig = config[platform] || config.other;

    if (apiKeyLabel) apiKeyLabel.textContent = platformConfig.apiKey;
    if (apiSecretLabel) apiSecretLabel.textContent = platformConfig.apiSecret;
    if (apiKeyHelp) apiKeyHelp.textContent = platformConfig.apiKeyHelp;
    if (identifierLabel) identifierLabel.textContent = platformConfig.identifier;
    if (identifierHelp) identifierHelp.textContent = platformConfig.identifierHelp;

    if (identifierSection) {
      identifierSection.style.display = platformConfig.showIdentifier ? 'block' : 'none';
    }
    if (gatewaySection) {
      gatewaySection.style.display = platformConfig.showGateway ? 'block' : 'none';
    }
    if (webhookInstructions) {
      webhookInstructions.style.display = platformConfig.showWebhook ? 'block' : 'none';
    }
    if (platformConfig.showWebhook) {
      if (setupTitle) setupTitle.textContent = platformConfig.setupTitle;
      if (setupDesc) setupDesc.textContent = platformConfig.setupDesc;
    }
  }

  async function handleSocialSubmit(event) {
    event.preventDefault();

    const platform = document.getElementById('socialPlatform')?.value || 'whatsapp';
    const gateway = document.getElementById('whatsappGateway')?.value || 'meta_cloud_api';

    const formData = new FormData(socialConnectionForm);
    formData.append('action', 'save_social');
    formData.append('channel', platform);
    formData.append('provider', platform === 'whatsapp' ? gateway : platform);

    const submitBtn = document.getElementById('saveSocialBtn');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Saving...';
    }

    setSocialStatus('info', `Saving ${platform} configuration...`);

    try {
      const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
      const response = await fetch('/integrations/webhooks', {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
        body: formData,
      });

      if (response.ok) {
        setSocialStatus('success', `✅ ${platform} connected successfully! Your social messaging integration is now active.`);

        // Mark social channel as connected
        await handleSourceConnect('social', socialConnectTriggerBtn);

        setTimeout(() => {
          closeSocialModal();
          setConnectSourcesStatus('success', `Social messaging connected via ${platform}`);
        }, 2000);
      } else {
        const data = await response.json().catch(() => ({}));
        setSocialStatus('error', data.error || data.message || `Failed to save ${platform} configuration`);
      }
    } catch (err) {
      setSocialStatus('error', err.message || 'Network error. Please try again.');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save & Connect';
      }
    }
  }

  function openChatModal(triggerBtn) {
    if (!chatConnectModal) return;
    chatConnectTriggerBtn = triggerBtn || null;
    if (chatConnectStatus) chatConnectStatus.textContent = '';

    // Close user menu if open
    const userMenu = document.getElementById('userMenu');
    if (userMenu && !userMenu.classList.contains('hidden')) {
      userMenu.classList.add('hidden');
    }

    // Hide main content and header
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) mainEl.style.visibility = 'hidden';
    if (headerEl) headerEl.style.visibility = 'hidden';

    chatConnectModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeChatModal() {
    if (!chatConnectModal) return;
    chatConnectModal.classList.add('hidden');
    document.body.style.overflow = '';

    // Restore visibility
    const mainEl = document.querySelector('main');
    const headerEl = document.querySelector('header');
    if (mainEl) mainEl.style.visibility = '';
    if (headerEl) headerEl.style.visibility = '';

    // Reset form
    if (chatConnectionForm) chatConnectionForm.reset();
    if (chatConnectStatus) chatConnectStatus.classList.add('hidden');

    // Reset to default view (InboxIQ Native)
    const inboxiqSection = document.getElementById('inboxiqChatSection');
    const externalSection = document.getElementById('externalChatSection');
    const platformSelect = document.getElementById('chatPlatform');
    if (platformSelect) platformSelect.value = 'inboxiq';
    if (inboxiqSection) inboxiqSection.style.display = 'block';
    if (externalSection) externalSection.classList.add('hidden');
  }

  function setChatStatus(type, message) {
    if (!chatConnectStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    chatConnectStatus.className = `text-xs px-4 py-3 rounded-xl border ${map[type] || map.info}`;
    chatConnectStatus.textContent = message;
    chatConnectStatus.classList.remove('hidden');
  }

  function updateChatLabels(platform) {
    const inboxiqSection = document.getElementById('inboxiqChatSection');
    const externalSection = document.getElementById('externalChatSection');
    const apiKeyLabel = document.getElementById('chatApiKeyLabel');
    const apiSecretLabel = document.getElementById('chatApiSecretLabel');
    const apiKeyHelp = document.getElementById('chatApiKeyHelp');
    const webhookInstructions = document.getElementById('chatWebhookInstructions');
    const setupTitle = document.getElementById('chatSetupTitle');
    const setupDesc = document.getElementById('chatSetupDesc');

    // Show/hide sections based on platform
    const isNative = platform === 'inboxiq';
    if (inboxiqSection) inboxiqSection.style.display = isNative ? 'block' : 'none';
    if (externalSection) {
      if (isNative) {
        externalSection.classList.add('hidden');
      } else {
        externalSection.classList.remove('hidden');
      }
    }

    // Platform-specific configurations for external platforms
    const config = {
      intercom: {
        apiKey: 'Intercom App ID',
        apiSecret: 'Access Token',
        apiKeyHelp: 'Find this in Intercom → Settings → App Settings.',
        showWebhook: true,
        setupTitle: 'Intercom Webhook Setup',
        setupDesc: 'Configure webhook in Intercom → Settings → Webhooks:',
      },
      drift: {
        apiKey: 'Drift OAuth App ID',
        apiSecret: 'OAuth Token',
        apiKeyHelp: 'Find this in Drift → Settings → App Credentials.',
        showWebhook: true,
        setupTitle: 'Drift Webhook Setup',
        setupDesc: 'Configure webhook in Drift → Settings → Webhooks:',
      },
      zendesk: {
        apiKey: 'Zendesk API Key',
        apiSecret: 'API Token',
        apiKeyHelp: 'Find this in Zendesk Admin → Channels → API.',
        showWebhook: true,
        setupTitle: 'Zendesk Chat Webhook',
        setupDesc: 'Configure webhook in Zendesk Chat settings:',
      },
      freshchat: {
        apiKey: 'Freshchat App ID',
        apiSecret: 'API Token',
        apiKeyHelp: 'Find this in Freshchat → Settings → API Tokens.',
        showWebhook: true,
        setupTitle: 'Freshchat Webhook Setup',
        setupDesc: 'Configure webhook in Freshchat settings:',
      },
      crisp: {
        apiKey: 'Crisp Website ID',
        apiSecret: 'API Key',
        apiKeyHelp: 'Find this in Crisp → Website Settings → Setup.',
        showWebhook: true,
        setupTitle: 'Crisp Webhook Setup',
        setupDesc: 'Configure webhook in Crisp Integrations:',
      },
      livechat: {
        apiKey: 'LiveChat Account ID',
        apiSecret: 'Access Token',
        apiKeyHelp: 'Find this in LiveChat → Settings → Integrations.',
        showWebhook: true,
        setupTitle: 'LiveChat Webhook Setup',
        setupDesc: 'Configure webhook in LiveChat settings:',
      },
      olark: {
        apiKey: 'Olark Site ID',
        apiSecret: 'API Key',
        apiKeyHelp: 'Find this in Olark → Settings → Integrations.',
        showWebhook: true,
        setupTitle: 'Olark Webhook Setup',
        setupDesc: 'Configure webhook in Olark settings:',
      },
      other: {
        apiKey: 'API Key / App ID',
        apiSecret: 'API Secret / Access Token',
        apiKeyHelp: 'Enter your chat platform\'s API credentials.',
        showWebhook: false,
      },
    };

    const platformConfig = config[platform] || config.other;

    if (apiKeyLabel) apiKeyLabel.textContent = platformConfig.apiKey;
    if (apiSecretLabel) apiSecretLabel.textContent = platformConfig.apiSecret;
    if (apiKeyHelp) apiKeyHelp.textContent = platformConfig.apiKeyHelp;

    if (webhookInstructions) {
      webhookInstructions.style.display = platformConfig.showWebhook ? 'block' : 'none';
    }
    if (platformConfig.showWebhook) {
      if (setupTitle) setupTitle.textContent = platformConfig.setupTitle;
      if (setupDesc) setupDesc.textContent = platformConfig.setupDesc;
    }
  }

  async function handleChatSubmit(event) {
    event.preventDefault();

    const platform = document.getElementById('chatPlatform')?.value || 'inboxiq';
    const isNative = platform === 'inboxiq';

    const formData = new FormData(chatConnectionForm);
    formData.append('action', 'save_chat');
    formData.append('platform', platform);

    const submitBtn = document.getElementById('saveChatBtn');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Saving...';
    }

    setChatStatus('info', `Saving ${isNative ? 'InboxIQ native chat' : platform} configuration...`);

    try {
      const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
      const response = await fetch('/integrations/webhooks', {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
        body: formData,
      });

      if (response.ok) {
        setChatStatus('success', `✅ ${isNative ? 'InboxIQ chat widget' : platform} connected successfully! Your chat integration is now active.`);

        // Mark chat channel as connected
        await handleSourceConnect('chat', chatConnectTriggerBtn);

        setTimeout(() => {
          closeChatModal();
          setConnectSourcesStatus('success', `Chat connected via ${isNative ? 'InboxIQ native widget' : platform}`);
        }, 2000);
      } else {
        const data = await response.json().catch(() => ({}));
        setChatStatus('error', data.error || data.message || `Failed to save ${platform} configuration`);
      }
    } catch (err) {
      setChatStatus('error', err.message || 'Network error. Please try again.');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save & Connect';
      }
    }
  }

  async function postJSON(url, body) {
    const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
    const headers = { 'Content-Type': 'application/json' };
    if (csrf) headers['X-CSRF-TOKEN'] = csrf;
    return fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: JSON.stringify(body || {}),
    });
  }

  async function getJSON(url) {
    return fetch(url, {
      method: 'GET',
      credentials: 'include',
    });
  }

  async function handleSourceConnect(channel, btn) {
    if (!channel) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Connecting...';
    }
    setConnectSourcesStatus('info', `Connecting ${channel}...`);
    try {
      const resp = await postJSON('/api/v1/inboxiq/source-connections', {
        channel,
        provider: channel,
        status: 'connected',
        metadata: { channel },
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.message || data.error || 'Unable to connect source.');
      }
      setConnectSourcesStatus('success', `${channel} marked as connected.`);
    } catch (err) {
      setConnectSourcesStatus('error', err.message || 'Failed to connect source.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Connect';
      }
    }
  }

  async function handleSourceTest(channel, btn) {
    if (!channel) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Testing...';
    }
    setConnectSourcesStatus('info', `Sending test event for ${channel}...`);
    try {
      const resp = await postJSON('/api/v1/inboxiq/connection-test', {
        channel,
        payload: {
          subject: `Connection test (${channel})`,
          body: `Test event from dashboard for ${channel}.`,
          from_email: 'dashboard@inboxiq.local',
          provider: channel,
        },
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.message || data.error || 'Unable to run test.');
      }
      setConnectSourcesStatus('success', `${channel} test queued (task ${data.task_id || 'queued'}).`);
    } catch (err) {
      setConnectSourcesStatus('error', err.message || 'Failed to send test event.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Test';
      }
    }
  }

  async function handleSend() {
    if (!sendBtn) return;
    const toEmail = (emailInput?.value || '').trim();
    if (!toEmail) {
      setStatus('error', 'Please enter a destination email.');
      return;
    }
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending...';
    setStatus('info', `Sending a test email to ${toEmail}...`);
    try {
      const response = await fetch('/api/test-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_email: toEmail }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Unable to send test email.');
      }
      setStatus('success', data.message || 'Test email sent.');
      if (Array.isArray(data.triage)) {
        renderTriage(data.triage);
      }
    } catch (err) {
      setStatus('error', err.message || 'Failed to send test email.');
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Send test email →';
    }
  }

  function renderTriage(items) {
    if (!triageResults || !triageList) return;
    triageList.innerHTML = '';
    items.forEach((item) => {
      const card = document.createElement('div');
      card.className = 'rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200';
      card.innerHTML = `
        <div class="flex items-center justify-between mb-1">
          <span class="font-semibold text-slate-100">${item.subject || 'Email'}</span>
          <span class="text-[11px] text-slate-400">${item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><span class="text-slate-400">Category:</span> ${item.category || '-'}</div>
          <div><span class="text-slate-400">Priority:</span> ${item.priority || '-'}</div>
          <div><span class="text-slate-400">Sentiment:</span> ${item.sentiment || '-'}</div>
          <div><span class="text-slate-400">Ticket:</span> ${item.ticket || '-'}</div>
        </div>
      `;
      triageList.appendChild(card);
    });
    triageResults.classList.remove('hidden');
  }

  if (sendBtn) {
    sendBtn.addEventListener('click', handleSend);
  }
  if (sourceConnectBtns.length) {
    sourceConnectBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        if (btn.dataset.channel === 'forms') {
          setConnectSourcesStatus('info', 'Opening forms connect…');
          openFormsModal(btn);
          return;
        }
        if (btn.dataset.channel === 'voice') {
          setConnectSourcesStatus('info', 'Opening Voice/IVR connect…');
          openTwilioModal(btn);
          return;
        }
        if (btn.dataset.channel === 'social') {
          setConnectSourcesStatus('info', 'Opening Social messaging connect…');
          openSocialModal(btn);
          return;
        }
        if (btn.dataset.channel === 'chat') {
          setConnectSourcesStatus('info', 'Opening Chat connect…');
          openChatModal(btn);
          return;
        }
        if (btn.dataset.channel === 'crm') {
          setConnectSourcesStatus('info', 'Opening CRM connect…');
          // Redirect to settings integrations page and auto-open CRM modal
          window.location.href = '/settings/integrations?openCrm=true';
          return;
        }
        if (btn.dataset.channel === 'api') {
          setConnectSourcesStatus('info', 'Opening API/Webhooks setup…');
          // Redirect to webhooks configuration page
          window.location.href = '/integrations/webhooks';
          return;
        }
        handleSourceConnect(btn.dataset.channel, btn);
      });
    });
  }
  if (formsConnectBtn) {
    formsConnectBtn.addEventListener('click', () => {
      setConnectSourcesStatus('info', 'Opening forms connect…');
      openFormsModal(formsConnectBtn);
    });
  }
  if (sourceTestBtns.length) {
    sourceTestBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        handleSourceTest(btn.dataset.channel, btn);
      });
    });
  }

  // Auto-refresh recent triage every 10 seconds
  let refreshInterval = null;

  function updateTwilioLabels(provider) {
    const accountIdLabel = document.getElementById('accountIdLabel');
    const authTokenLabel = document.getElementById('authTokenLabel');
    const accountIdHelp = document.getElementById('accountIdHelp');
    const accountIdInput = document.getElementById('accountIdInput');
    const webhookSetupTitle = document.getElementById('webhookSetupTitle');
    const webhookSetupDesc = document.getElementById('webhookSetupDesc');
    const webhookInstructions = document.getElementById('twilioWebhookInstructions');

    const labelMap = {
      twilio: {
        accountId: 'Twilio Account SID',
        authToken: 'Twilio Auth Token',
        help: 'Find this in your Twilio console dashboard.',
        placeholder: 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        showWebhook: true,
        webhookTitle: 'Twilio Webhook Setup',
        webhookDesc: 'After saving, configure your Twilio phone numbers to send webhooks to:',
      },
      tesco_mobile: {
        accountId: 'Tesco Mobile Account ID',
        authToken: 'API Token',
        help: 'Find this in your Tesco Mobile portal.',
        placeholder: 'Enter your account ID',
        showWebhook: false,
      },
      aircall: {
        accountId: 'Aircall API ID',
        authToken: 'Aircall API Token',
        help: 'Find this in Aircall Settings → Integrations & API.',
        placeholder: 'Enter your API ID',
        showWebhook: false,
      },
      dialpad: {
        accountId: 'Dialpad API Key',
        authToken: 'API Secret',
        help: 'Find this in Dialpad Admin → Integrations.',
        placeholder: 'Enter your API key',
        showWebhook: false,
      },
      five9: {
        accountId: 'Five9 Account ID',
        authToken: 'API Key',
        help: 'Find this in Five9 Admin Console → API Credentials.',
        placeholder: 'Enter your account ID',
        showWebhook: false,
      },
      other: {
        accountId: 'Account ID / API Key',
        authToken: 'Auth Token / API Secret',
        help: 'Enter your provider\'s authentication credentials.',
        placeholder: 'Enter your account identifier',
        showWebhook: false,
      },
    };

    const config = labelMap[provider] || labelMap.other;

    if (accountIdLabel) accountIdLabel.textContent = config.accountId;
    if (authTokenLabel) authTokenLabel.textContent = config.authToken;
    if (accountIdHelp) accountIdHelp.textContent = config.help;
    if (accountIdInput) accountIdInput.placeholder = config.placeholder;

    if (webhookInstructions) {
      webhookInstructions.style.display = config.showWebhook ? 'block' : 'none';
    }
    if (config.showWebhook) {
      if (webhookSetupTitle) webhookSetupTitle.textContent = config.webhookTitle;
      if (webhookSetupDesc) webhookSetupDesc.textContent = config.webhookDesc;
    }
  }

  function bindTwilioModalHandlers() {
    // Close modal button
    if (closeTwilioModalBtn) {
      closeTwilioModalBtn.addEventListener('click', closeTwilioModal);
    }
    // Cancel button
    if (cancelTwilioModalBtn) {
      cancelTwilioModalBtn.addEventListener('click', closeTwilioModal);
    }
    // Close on backdrop click
    if (twilioModalBackdrop) {
      twilioModalBackdrop.addEventListener('click', closeTwilioModal);
    }
    // Form submission
    if (twilioConnectionForm) {
      twilioConnectionForm.addEventListener('submit', handleTwilioSubmit);
    }
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && twilioConnectModal && !twilioConnectModal.classList.contains('hidden')) {
        closeTwilioModal();
      }
    });

    // Update labels when provider changes
    const providerSelect = document.getElementById('twilioProvider');
    if (providerSelect) {
      providerSelect.addEventListener('change', (e) => {
        updateTwilioLabels(e.target.value);
      });
      // Initialize with current selection
      updateTwilioLabels(providerSelect.value);
    }
  }

  function bindFormsModalHandlers() {
    // Close modal button
    if (closeFormsModalBtn) {
      closeFormsModalBtn.addEventListener('click', closeFormsModal);
    }
    // Close on backdrop click
    if (formsModalBackdrop) {
      formsModalBackdrop.addEventListener('click', closeFormsModal);
    }
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && formsConnectModal && !formsConnectModal.classList.contains('hidden')) {
        closeFormsModal();
      }
    });

    // Populate URLs
    if (formsIntakeUrlModal) {
      const origin = window.location.origin.replace('127.0.0.1', 'api.kalevent.com').replace(':8000', '');
      formsIntakeUrlModal.value = `${origin}/api/v1/intake`;
    }
    if (formsShimUrlModal) {
      const origin = window.location.origin.replace('127.0.0.1', 'api.kalevent.com').replace(':8000', '');
      formsShimUrlModal.value = `${origin}/api/v1/intake/shim`;
    }

    // Copy buttons
    if (formsCopyBtns.length) {
      formsCopyBtns.forEach((btn) => {
        btn.addEventListener('click', async () => {
          const targetId = btn.dataset.copyTarget;
          const target = targetId ? document.getElementById(targetId) : null;
          const value = target?.value || target?.textContent || '';
          if (!value) return;
          try {
            await navigator.clipboard.writeText(value);
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
          } catch (err) {
            btn.textContent = 'Failed';
            setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
          }
        });
      });
    }

    // Mark connected button
    if (markFormsConnectedModal) {
      markFormsConnectedModal.addEventListener('click', async () => {
        if (formsConnectStatusModal) formsConnectStatusModal.textContent = 'Marking connected...';
        await handleSourceConnect('forms', formsConnectTriggerBtn);
        if (formsConnectStatusModal) {
          formsConnectStatusModal.textContent = '✅ Forms marked as connected.';
          formsConnectStatusModal.className = 'text-xs text-emerald-400';
        }
        setTimeout(closeFormsModal, 1500);
      });
    }
  }

  function bindSocialModalHandlers() {
    // Close modal button
    if (closeSocialModalBtn) {
      closeSocialModalBtn.addEventListener('click', closeSocialModal);
    }
    // Cancel button
    if (cancelSocialModalBtn) {
      cancelSocialModalBtn.addEventListener('click', closeSocialModal);
    }
    // Close on backdrop click
    if (socialModalBackdrop) {
      socialModalBackdrop.addEventListener('click', closeSocialModal);
    }
    // Form submission
    if (socialConnectionForm) {
      socialConnectionForm.addEventListener('submit', handleSocialSubmit);
    }
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && socialConnectModal && !socialConnectModal.classList.contains('hidden')) {
        closeSocialModal();
      }
    });

    // Update labels when platform or gateway changes
    const platformSelect = document.getElementById('socialPlatform');
    const gatewaySelect = document.getElementById('whatsappGateway');

    if (platformSelect) {
      platformSelect.addEventListener('change', (e) => {
        const gateway = gatewaySelect?.value || 'meta_cloud_api';
        updateSocialLabels(e.target.value, gateway);
      });
    }

    if (gatewaySelect) {
      gatewaySelect.addEventListener('change', (e) => {
        const platform = platformSelect?.value || 'whatsapp';
        updateSocialLabels(platform, e.target.value);
      });
    }

    // Initialize with current selection
    if (platformSelect && gatewaySelect) {
      updateSocialLabels(platformSelect.value, gatewaySelect.value);
    }
  }

  function bindChatModalHandlers() {
    // Close modal button
    if (closeChatModalBtn) {
      closeChatModalBtn.addEventListener('click', closeChatModal);
    }
    // Cancel button
    if (cancelChatModalBtn) {
      cancelChatModalBtn.addEventListener('click', closeChatModal);
    }
    // Close on backdrop click
    if (chatModalBackdrop) {
      chatModalBackdrop.addEventListener('click', closeChatModal);
    }
    // Form submission
    if (chatConnectionForm) {
      chatConnectionForm.addEventListener('submit', handleChatSubmit);
    }
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && chatConnectModal && !chatConnectModal.classList.contains('hidden')) {
        closeChatModal();
      }
    });

    // Update labels and sections when platform changes
    const platformSelect = document.getElementById('chatPlatform');
    if (platformSelect) {
      platformSelect.addEventListener('change', (e) => {
        updateChatLabels(e.target.value);
      });
      // Initialize with current selection
      updateChatLabels(platformSelect.value);
    }

    // Copy embed code button
    const copyChatEmbedCodeBtn = document.getElementById('copyChatEmbedCode');
    if (copyChatEmbedCodeBtn) {
      copyChatEmbedCodeBtn.addEventListener('click', async () => {
        const embedCode = document.getElementById('chatEmbedCode');
        const value = embedCode?.textContent || '';
        if (!value) return;
        try {
          await navigator.clipboard.writeText(value);
          copyChatEmbedCodeBtn.textContent = 'Copied!';
          setTimeout(() => { copyChatEmbedCodeBtn.textContent = 'Copy'; }, 2000);
        } catch (err) {
          copyChatEmbedCodeBtn.textContent = 'Failed';
          setTimeout(() => { copyChatEmbedCodeBtn.textContent = 'Copy'; }, 2000);
        }
      });
    }
  }

  bindFormsModalHandlers();
  bindTwilioModalHandlers();
  bindSocialModalHandlers();
  bindChatModalHandlers();

  async function refreshTickets() {
    try {
      const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const resp = await fetch('/api/v1/inboxiq/tickets?page_size=5', {
        headers,
        credentials: 'include',
      });
      const data = await resp.json();
      if (resp.ok && data.tickets) {
        renderTriage(data.tickets);
      } else if (resp.status === 401) {
        setStatus('error', 'Please sign in to view live triage.');
        if (refreshInterval) {
          clearInterval(refreshInterval);
          refreshInterval = null;
        }
      }
    } catch (err) {
      // silent
    }
  }
  refreshInterval = setInterval(refreshTickets, 10000);
  refreshTickets();

  async function startConnect(provider) {
    const url = provider === 'gmail' ? '/api/v1/auth/google/inbox/start' : '/api/v1/auth/outlook/inbox/start';
    connectStatus.textContent = `Connecting to ${provider}...`;
    window.location = url;
  }

  function applyPollMeta(lp, health) {
    if (!lastPollLine) return;
    if (lp?.last_poll_at) {
      lastKnownPollAt = lp.last_poll_at;
      let text = `Last poll: ${lp.last_poll_at}`;
      if (lp.last_poll_status) text += ` (${lp.last_poll_status})`;
      if (lp.last_poll_error) text += ` • Error: ${lp.last_poll_error}`;
      lastPollLine.textContent = text;
    } else if (lp?.last_poll_status && lp.last_poll_status !== 'never') {
      let text = `Last poll: ${lp.last_poll_status}`;
      if (lp.last_poll_error) text += ` • Error: ${lp.last_poll_error}`;
      lastPollLine.textContent = text;
    } else if (lastKnownPollAt && lastPollLine.textContent.includes('not yet polled')) {
      lastPollLine.textContent = `Last poll: ${lastKnownPollAt}`;
    }
    const badge = document.getElementById('pollHealthBadge');
    if (badge) {
      let status = health?.status || 'unknown';
      const effectivePollAt = lp?.last_poll_at || lastKnownPollAt;
      if (effectivePollAt && (status === 'never' || status === 'unknown')) {
        const ts = Date.parse(effectivePollAt);
        if (!Number.isNaN(ts)) {
          const ageMin = (Date.now() - ts) / 60000;
          const staleMinutes = Number(health?.stale_minutes ?? 30);
          status = ageMin > staleMinutes ? 'stale' : 'ok';
        }
      }
      badge.textContent = status === 'ok' ? 'healthy' : status;
      badge.className = 'text-slate-400';
      if (status === 'ok') badge.className = 'text-emerald-300';
      else if (status === 'stale') badge.className = 'text-amber-300';
      else if (status === 'error') badge.className = 'text-rose-300';
    }
  }

  // One-time poll trigger when a connection exists
  async function pollInboxOnce() {
    const connectionId = getConnectionId();
    if (!connectionId) return;
    try {
      const resp = await getJSON(`/api/v1/inboxiq/poll/${connectionId}`);
      const contentType = resp.headers.get('content-type') || '';
      const data = contentType.includes('application/json') ? await resp.json() : {};
      if (resp.ok) {
        if (connectStatus) {
          connectStatus.textContent = `Polled inbox: ${data.summary?.created ?? 0} new, ${data.summary?.duplicates ?? 0} duplicates, ${data.summary?.errors ?? 0} errors.`;
        }
        applyPollMeta(data.last_poll, data.poll_health);
        await refreshLastPoll();
      } else if (connectStatus) {
        connectStatus.textContent = data.error || `Polling failed (HTTP ${resp.status})`;
      }
    } catch (err) {
      if (connectStatus) connectStatus.textContent = 'Connected — polling in the background.';
    }
  }
  pollInboxOnce();

  // Refresh last poll info from server metadata
  async function refreshLastPoll() {
    if (!lastPollLine) return;
    try {
      const resp = await fetch('/api/v1/inboxiq/connections/mine', { credentials: 'include' });
      const contentType = resp.headers.get('content-type') || '';
      const data = contentType.includes('application/json') ? await resp.json() : {};
      if (!resp.ok) return;
      const lp = data.last_poll || {};
      const health = data.poll_health || {};
      const apiConnectionId = data.connection?.id;
      if (!autoPollAttempted && (lp.last_poll_status === 'never' || !lp.last_poll_status) && apiConnectionId) {
        autoPollAttempted = true;
        try {
          await getJSON(`/api/v1/inboxiq/poll/${apiConnectionId}`);
          await refreshLastPoll();
        } catch (_) {
          // ignore auto-poll failures
        }
      }
      applyPollMeta(lp, health);
    } catch (err) {
      // silent
    }
  }
  refreshLastPoll();

  function setActiveDashboardTab(target) {
    dashboardTabs.forEach((btn) => {
      const isActive = btn.dataset.dashboardSection === target;
      btn.classList.toggle('bg-indigo-500/20', isActive);
      btn.classList.toggle('border-indigo-400', isActive);
      btn.classList.toggle('text-indigo-100', isActive);
      btn.classList.toggle('bg-slate-900/40', !isActive);
      btn.classList.toggle('border-slate-800', !isActive);
      btn.classList.toggle('text-slate-300', !isActive);
    });
    dashboardPanels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.dashboardSectionPanel !== target);
    });
    if (target === 'training') {
      loadTrainingMetrics();
      loadTrainingStatus();
    }
  }

  if (dashboardTabs.length && dashboardPanels.length) {
    const defaultTab = 'connections';
    const initial = dashboardTabs.find((btn) => btn.dataset.dashboardSection === defaultTab);
    if (initial) setActiveDashboardTab(defaultTab);
    dashboardTabs.forEach((btn) => {
      btn.addEventListener('click', () => {
        setActiveDashboardTab(btn.dataset.dashboardSection);
      });
    });
  }

  function setActiveFeedbackTab(target) {
    feedbackTabs.forEach((btn) => {
      const isActive = btn.dataset.feedbackSection === target;
      btn.classList.toggle('bg-indigo-500/20', isActive);
      btn.classList.toggle('border-indigo-400', isActive);
      btn.classList.toggle('text-indigo-100', isActive);
      btn.classList.toggle('bg-slate-900/40', !isActive);
      btn.classList.toggle('border-slate-800', !isActive);
      btn.classList.toggle('text-slate-300', !isActive);
    });
    feedbackPanels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.feedbackPanel !== target);
    });
  }

  if (feedbackTabs.length && feedbackPanels.length) {
    const defaultFeedback = 'testimonial';
    const initialFeedback = feedbackTabs.find((btn) => btn.dataset.feedbackSection === defaultFeedback);
    if (initialFeedback) setActiveFeedbackTab(defaultFeedback);
    feedbackTabs.forEach((btn) => {
      btn.addEventListener('click', () => {
        setActiveFeedbackTab(btn.dataset.feedbackSection);
      });
    });
  }

  // Ticket search + filters
  const searchForm = document.getElementById('ticketSearchForm');
  const qInput = document.getElementById('ticketSearchQuery');
  const statusInput = document.getElementById('ticketStatus');
  const categoryInput = document.getElementById('ticketCategory');
  const priorityInput = document.getElementById('ticketPriority');
  const afterInput = document.getElementById('ticketAfter');
  const beforeInput = document.getElementById('ticketBefore');
  const ticketResults = document.getElementById('ticketResults');
  const ticketStatus = document.getElementById('ticketSearchStatus');
  const testimonialMsg = document.getElementById('testimonialMessage');
  const testimonialRating = document.getElementById('testimonialRating');
  const testimonialConsent = document.getElementById('testimonialConsent');
  const testimonialStatus = document.getElementById('testimonialStatus');
  const submitTestimonialBtn = document.getElementById('submitTestimonialBtn');
  const actionSearchInput = document.getElementById('actionSearchInput');
  const actionPriorityFilter = document.getElementById('actionPriorityFilter');
  let actionCards = Array.from(document.querySelectorAll('.action-card'));
  const actionCountSpan = document.getElementById('actionRequiredCount');
  const impactScope = document.getElementById('impactScope');
  const showActionOnlyToggle = document.getElementById('showActionOnly');
  const actionOnlyHint = document.getElementById('actionOnlyHint');
  const actionRequiredList = document.getElementById('actionRequiredList');
  const optionalList = document.getElementById('optionalList');
  const autoHandledEmailList = document.getElementById('autoHandledEmailList');
  const autoHandledFeedbackList = document.getElementById('autoHandledFeedbackList');
  const showDraftOnly = document.getElementById('showDraftOnly');
  const metricActionRequired = document.getElementById('metricActionRequired');
  const metricOptional = document.getElementById('metricOptional');
  const metricAutoHandledQueue = document.getElementById('metricAutoHandledQueue');
  const metricDecisionTotal = document.getElementById('metricDecisionTotal');
  const metricEscalated = document.getElementById('metricEscalated');
  const metricNeedsReview = document.getElementById('metricNeedsReview');
  const metricAutoHandledRate = document.getElementById('metricAutoHandledRate');
  const metricDecisionTime = document.getElementById('metricDecisionTime');
  const metricSlaRisk = document.getElementById('metricSlaRisk');
  const useCaseTabs = Array.from(document.querySelectorAll('.use-case-tab'));
  const channelFilter = document.getElementById('channelFilter');
  const trainingStatus = document.getElementById('trainingStatus');
  const trainingLastRun = document.getElementById('trainingLastRun');
  const trainingProvider = document.getElementById('trainingProvider');
  const trainingModel = document.getElementById('trainingModel');
  const trainingSamples = document.getElementById('trainingSamples');
  const trainingTrainAcc = document.getElementById('trainingTrainAcc');
  const trainingEvalAcc = document.getElementById('trainingEvalAcc');
  const trainingTable = document.getElementById('trainingTable');
  const runTrainingBtn = document.getElementById('runTrainingBtn');
  const runTrainingBtnText = document.getElementById('runTrainingBtnText');
  const runTrainingSpinner = document.getElementById('runTrainingSpinner');
  const trainingReadiness = document.getElementById('trainingReadiness');
  let trainingLoaded = false;
  let activeUseCase = 'all';

  function setTicketStatus(kind, msg) {
    if (!ticketStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    ticketStatus.className = `text-xs rounded-xl px-3 py-2 border ${map[kind] || map.info}`;
    ticketStatus.textContent = msg;
    ticketStatus.classList.remove('hidden');
  }

  function setTrainingStatus(kind, msg) {
    if (!trainingStatus) return;
    const map = {
      success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-400/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-400/40 bg-indigo-500/10 text-indigo-100',
    };
    trainingStatus.className = `text-xs rounded-xl px-3 py-2 border ${map[kind] || map.info}`;
    trainingStatus.textContent = msg;
    trainingStatus.classList.remove('hidden');
  }

  function renderTrainingTable(rows = []) {
    if (!trainingTable) return;
    if (!rows.length) {
      trainingTable.innerHTML = '<div class="px-4 py-3 text-slate-400">No training runs yet.</div>';
      return;
    }
    trainingTable.innerHTML = rows
      .map((row) => {
        const created = row.created_at ? new Date(row.created_at).toLocaleString() : '—';
        const trainAcc = row.train_accuracy != null ? `${Math.round(row.train_accuracy * 100)}%` : '—';
        const evalAcc = row.eval_accuracy != null ? `${Math.round(row.eval_accuracy * 100)}%` : '—';
        return `
          <div class="px-4 py-3 grid grid-cols-1 md:grid-cols-6 gap-2">
            <div class="text-slate-200">${created}</div>
            <div>Provider: <span class="text-slate-200">${row.provider || '—'}</span></div>
            <div>Model: <span class="text-slate-200">${row.model_id || '—'}</span></div>
            <div>Samples: <span class="text-slate-200">${row.sample_count ?? 0}</span></div>
            <div>Train: <span class="text-slate-200">${trainAcc}</span></div>
            <div>Eval: <span class="text-slate-200">${evalAcc}</span></div>
          </div>
        `;
      })
      .join('');
  }

  async function loadTrainingMetrics() {
    if (trainingLoaded) return;
    if (!trainingTable) return;
    try {
      const resp = await fetch('/api/v1/inboxiq/training-metrics', { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Unable to load training metrics');
      const latest = data.latest || {};
      if (trainingLastRun) trainingLastRun.textContent = latest.created_at ? new Date(latest.created_at).toLocaleString() : '—';
      if (trainingProvider) trainingProvider.textContent = latest.provider || '—';
      if (trainingModel) trainingModel.textContent = latest.model_id || '—';
      if (trainingSamples) trainingSamples.textContent = latest.sample_count ?? '—';
      if (trainingTrainAcc) trainingTrainAcc.textContent = latest.train_accuracy != null ? `${Math.round(latest.train_accuracy * 100)}%` : '—';
      if (trainingEvalAcc) trainingEvalAcc.textContent = latest.eval_accuracy != null ? `${Math.round(latest.eval_accuracy * 100)}%` : '—';
      renderTrainingTable(data.metrics || []);
      trainingLoaded = true;
    } catch (err) {
      setTrainingStatus('error', err.message || 'Failed to load training metrics.');
    }
  }

  async function loadTrainingStatus() {
    if (!runTrainingBtn) return;
    try {
      const resp = await fetch('/api/v1/inboxiq/training/status', { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) {
        runTrainingBtn.disabled = true;
        if (trainingReadiness) trainingReadiness.textContent = 'Unable to check status';
        return;
      }

      if (data.can_train) {
        runTrainingBtn.disabled = false;
        if (trainingReadiness) {
          trainingReadiness.textContent = `${data.override_count} overrides + ${data.seed_count} seeds ready`;
          trainingReadiness.className = 'text-xs text-emerald-400';
        }
      } else {
        runTrainingBtn.disabled = true;
        if (trainingReadiness) {
          trainingReadiness.textContent = `Need ${data.samples_needed} more samples (${data.override_count}/${data.min_samples})`;
          trainingReadiness.className = 'text-xs text-amber-400';
        }
      }
    } catch (err) {
      runTrainingBtn.disabled = true;
      if (trainingReadiness) trainingReadiness.textContent = 'Status unavailable';
    }
  }

  async function triggerTraining() {
    if (!runTrainingBtn) return;

    runTrainingBtn.disabled = true;
    if (runTrainingBtnText) runTrainingBtnText.textContent = 'Queuing...';
    if (runTrainingSpinner) runTrainingSpinner.classList.remove('hidden');

    try {
      const csrfToken = getCookie('csrf_access_token');
      const resp = await fetch('/api/v1/inboxiq/training/trigger', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-TOKEN': csrfToken ? decodeURIComponent(csrfToken) : '',
        },
      });
      const data = await resp.json();

      if (resp.ok) {
        setTrainingStatus('success', data.message || 'Training queued successfully');
        if (runTrainingBtnText) runTrainingBtnText.textContent = 'Queued!';
        setTimeout(() => {
          if (runTrainingBtnText) runTrainingBtnText.textContent = 'Run Training';
          loadTrainingStatus();
        }, 3000);
      } else {
        setTrainingStatus('error', data.message || 'Failed to queue training');
        if (runTrainingBtnText) runTrainingBtnText.textContent = 'Run Training';
        runTrainingBtn.disabled = false;
      }
    } catch (err) {
      setTrainingStatus('error', 'Network error. Please try again.');
      if (runTrainingBtnText) runTrainingBtnText.textContent = 'Run Training';
      runTrainingBtn.disabled = false;
    } finally {
      if (runTrainingSpinner) runTrainingSpinner.classList.add('hidden');
    }
  }

  if (runTrainingBtn) {
    runTrainingBtn.addEventListener('click', triggerTraining);
  }

  function applyActionFilters() {
    loadDashboardData();
  }

  function updateActionOnlyHint() {
    if (!actionOnlyHint || !showActionOnlyToggle) return;
    actionOnlyHint.classList.toggle('hidden', !showActionOnlyToggle.checked);
  }

  if (actionSearchInput) {
    actionSearchInput.addEventListener('input', () => {
      applyActionFilters();
    });
  }
  if (actionPriorityFilter) {
    actionPriorityFilter.addEventListener('change', applyActionFilters);
  }
  if (impactScope) {
    impactScope.addEventListener('change', loadDashboardData);
  }
  if (showActionOnlyToggle) {
    showActionOnlyToggle.addEventListener('change', () => {
      updateActionOnlyHint();
      loadDashboardData();
    });
  }
  if (showDraftOnly) {
    showDraftOnly.addEventListener('change', loadDashboardData);
  }
  if (channelFilter) {
    channelFilter.addEventListener('change', loadDashboardData);
  }
  if (useCaseTabs.length) {
    const setActiveUseCase = (useCase, shouldLoad = true) => {
      activeUseCase = useCase || 'all';
      useCaseTabs.forEach((tab) => {
        const isActive = tab.dataset.useCase === activeUseCase;
        tab.classList.toggle('bg-indigo-500/20', isActive);
        tab.classList.toggle('border-indigo-400', isActive);
        tab.classList.toggle('text-indigo-100', isActive);
        tab.classList.toggle('bg-slate-900/40', !isActive);
        tab.classList.toggle('border-slate-800', !isActive);
        tab.classList.toggle('text-slate-300', !isActive);
      });
      if (shouldLoad) loadDashboardData();
    };

    useCaseTabs.forEach((btn) => {
      btn.addEventListener('click', () => setActiveUseCase(btn.dataset.useCase || 'all'));
    });
    // Set default so the active CTA is clearly highlighted on load.
    setActiveUseCase('all', false);
  }

  function updateMetrics(counts = {}) {
    if (metricActionRequired) metricActionRequired.textContent = counts.action_required ?? 0;
    if (metricOptional) metricOptional.textContent = counts.optional ?? 0;
    if (metricAutoHandledQueue) metricAutoHandledQueue.textContent = counts.auto_handled ?? 0;
    const total =
      (counts.action_required ?? 0) +
      (counts.optional ?? 0) +
      (counts.auto_handled ?? 0) +
      (counts.auto_handled_feedback ?? 0);
    if (metricDecisionTotal) metricDecisionTotal.textContent = total;
    if (metricEscalated) metricEscalated.textContent = counts.action_required ?? 0;
    if (metricNeedsReview) metricNeedsReview.textContent = counts.optional ?? 0;
    if (metricAutoHandledRate) metricAutoHandledRate.textContent = `${counts.triage_eliminated_pct ?? 0}%`;
    if (metricDecisionTime) metricDecisionTime.textContent = `${counts.decision_time_avg_minutes ?? 0}m`;
    if (metricSlaRisk) metricSlaRisk.textContent = counts.sla_risk_count ?? 0;
    if (actionCountSpan) actionCountSpan.textContent = `(${counts.action_required ?? 0})`;
  }

  function normalizeValue(val, fallback) {
    return (val || fallback || '').toString().toLowerCase();
  }

  function buildQueueCard(item, kind = 'action') {
    const useCase = normalizeValue(item.use_case, 'support');
    const channel = normalizeValue(item.channel, 'email');
    const decisionType = item.decision_type || 'triage';
    const decisionOutcome =
      item.decision_outcome ||
      (kind === 'action' ? 'action_required' : kind === 'optional' ? 'needs_review' : 'auto_handled');
    const decisionOutcomeLabel =
      decisionOutcome === 'auto_handled'
        ? 'Auto-handled'
        : decisionOutcome === 'needs_review'
        ? 'Needs review'
        : 'Action Required';
    const confidence =
      typeof item.confidence === 'number'
        ? `${Math.round(item.confidence * 100)}%`
        : item.confidence && typeof item.confidence === 'object'
        ? '—'
        : '—';
    const trace = Array.isArray(item.decision_trace) && item.decision_trace.length
      ? item.decision_trace.join(', ')
      : '';
    const decisionDetails = [
      item.entities_json ? `Entities: ${item.entities_json}` : '',
      item.route_json ? `Route: ${item.route_json}` : '',
      item.workflow_json ? `Workflow: ${item.workflow_json}` : '',
      item.escalation_json ? `Escalation: ${item.escalation_json}` : '',
    ].filter(Boolean).join(' • ');

    const badge = kind === 'action' ? 'Action Required' : kind === 'optional' ? 'Optional' : 'INFO';
    const badgeClass =
      kind === 'action'
        ? 'badge-primary'
        : kind === 'optional'
        ? 'badge-optional'
        : 'text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-700/40 text-slate-300 border border-slate-700';
    const priority = (item.priority || 'P2').toUpperCase();
    const priorityBadge = `<span class="badge-pill badge-priority badge-priority-${priority.toLowerCase()}">${priority}</span>`;
    const subject = item.subject || 'Decision';
    const provider = item.provider ? `<span>·</span><span>Provider: <span class="text-slate-200">${item.provider}</span></span>` : '';
    const aiReason = item.ai_reason || (kind === 'auto' ? 'Informational / auto-handled.' : 'Action required — customer needs help.');
    const owner = item.owner || 'Support';
    const team = item.team ? `Team: <span class="text-slate-300 font-semibold">${item.team}</span>` : '';
    const sla = item.sla || item.due_at || '—';
    const openThreadLink = item.provider_url
      ? `<a href="${item.provider_url}" target="_blank" rel="noreferrer" class="text-slate-400 hover:text-slate-300 underline">Open source</a>`
      : '';
    const draftBadge = item.draft_reply
      ? '<span class="badge-pill border border-indigo-400/60 text-indigo-200 bg-indigo-500/10">DraftReply</span>'
      : '';
    const actionBadge =
      kind === 'auto'
        ? `<span class="${badgeClass}">${badge}</span>`
        : `<span class="badge-pill ${badgeClass}">${badge}</span>`;
    const risk = item.risk_flag ? 'flagged' : 'none';

    if (kind === 'auto') {
      return `
        <div class="p-4 bg-slate-950/40" data-use-case="${useCase}" data-channel="${channel}">
          <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                ${actionBadge}
                <div class="font-semibold text-slate-200 truncate">${subject}</div>
                ${draftBadge}
              </div>
              <div class="text-xs text-slate-500 mt-1">
                Use case: <span class="text-slate-300">${useCase}</span>
                · Channel: <span class="text-slate-300">${channel}</span>
                · Decision: <span class="text-slate-300">${decisionType}</span>
              </div>
              <div class="text-xs text-slate-400 mt-2">
                <span class="font-semibold">Why this decision:</span>
                ${aiReason}
              </div>
              ${trace ? `<div class="text-xs text-slate-500 mt-1"><span class="font-semibold">Audit trail:</span> ${trace}</div>` : ''}
            </div>
            <div class="shrink-0 text-xs text-slate-500 flex flex-col gap-1 items-end text-right">
              <div>Owner: <span class="text-slate-300 font-semibold">${owner}</span></div>
              ${team ? `<div>${team}</div>` : ''}
              <div>SLA: <span class="text-slate-300 font-semibold">${sla}</span></div>
              <a href="${item.url || '#'}" class="text-slate-400 hover:text-slate-300 underline">View</a>
            </div>
          </div>
        </div>
      `;
    }

    return `
      <div
        class="rounded-2xl border border-slate-800 bg-slate-900/40 px-5 py-4 hover:bg-slate-900/50 transition action-card"
        data-priority="${priority}"
        data-text="${(subject + ' ' + (item.category || '') + ' ' + (item.intent || '') + ' ' + (item.sentiment || '')).toLowerCase()}"
        data-use-case="${useCase}"
        data-channel="${channel}"
      >
        <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-4 md:gap-6">
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              ${priorityBadge}
              ${actionBadge}
              <div class="font-semibold text-slate-50 truncate">${subject}</div>
              ${draftBadge}
            </div>
            <div class="text-xs text-slate-400 flex flex-wrap gap-2">
              <span>Use case: <span class="text-slate-200">${useCase}</span></span>
              <span>·</span>
              <span>Channel: <span class="text-slate-200">${channel}</span></span>
              <span>·</span>
              <span>Decision: <span class="text-slate-200">${decisionType}</span></span>
              <span>·</span>
              <span>Outcome: <span class="text-slate-200">${decisionOutcomeLabel}</span></span>
              <span>·</span>
              <span>Risk: <span class="text-slate-200">${risk}</span></span>
              ${provider}
            </div>
            <div class="text-sm text-slate-100">
              <span class="font-semibold text-slate-50">Why this decision:</span>
              ${aiReason}
            </div>
            ${trace ? `<div class="text-xs text-slate-400"><span class="font-semibold text-slate-300">Audit trail:</span> ${trace}</div>` : ''}
            ${decisionDetails ? `<div class="text-[11px] text-slate-400 mt-1"><span class="text-slate-500">Decision details:</span> ${decisionDetails}</div>` : ''}
          </div>
            <div class="shrink-0 text-xs text-slate-300 flex flex-col gap-1 items-end text-right">
              <div>Assigned: <span class="text-slate-50 font-semibold">${owner}</span></div>
              ${item.team ? `<div>Team: <span class="text-slate-50 font-semibold">${item.team}</span></div>` : ''}
              <div>SLA: <span class="text-slate-50 font-semibold">${sla}</span></div>
              <div>Confidence: <span class="text-slate-50 font-semibold">${confidence}</span></div>
              <a href="${item.url || '#'}" class="text-indigo-300 hover:text-indigo-200 underline underline-offset-2">Open ticket</a>
              ${openThreadLink}
            </div>
        </div>
      </div>
    `;
  }

  function renderList(listEl, items, kind) {
    if (!listEl) return;
    if (!items || !items.length) {
      listEl.innerHTML =
        kind === 'auto'
          ? '<div class="p-4 text-xs text-slate-400">No auto-handled items to show yet.</div>'
          : '<div class="px-5 py-4 text-sm text-slate-400 rounded-xl border border-slate-800 bg-slate-900/30">No items for this filter.</div>';
      return;
    }
    listEl.innerHTML = items.map((item) => buildQueueCard(item, kind)).join('');
    if (kind === 'action') {
      actionCards = Array.from(listEl.querySelectorAll('.action-card'));
    }
  }

  async function loadDashboardData() {
    const params = new URLSearchParams();
    if (impactScope?.value) params.set('scope', impactScope.value);
    if (actionPriorityFilter?.value) params.set('priority', actionPriorityFilter.value);
    if (actionSearchInput?.value) params.set('q', actionSearchInput.value.trim());
    if (showActionOnlyToggle && !showActionOnlyToggle.checked) params.set('action_only', 'false');
    if (showDraftOnly?.checked) params.set('draft_only', 'true');
    if (activeUseCase && activeUseCase !== 'all') params.set('use_case', activeUseCase);
    if (channelFilter?.value && channelFilter.value !== 'all') params.set('channel', channelFilter.value);

    try {
      const resp = await fetch(`/api/v1/inboxiq/dashboard-data?${params.toString()}`, { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Unable to load dashboard data');
      updateMetrics(data.counts || {});
      const useCaseFilter = activeUseCase || 'all';
      const channelValue = channelFilter?.value || 'all';
      const filterItems = (items = []) => {
        return items.filter((item) => {
          const itemUseCase = normalizeValue(item.use_case, 'support');
          const itemChannel = normalizeValue(item.channel, 'email');
          if (useCaseFilter !== 'all' && itemUseCase !== useCaseFilter) return false;
          if (channelValue !== 'all' && itemChannel !== channelValue) return false;
          if (showDraftOnly?.checked && !item.draft_reply) return false;
          return true;
        });
      };
      renderList(actionRequiredList, filterItems(data.action_required || []), 'action');
      renderList(optionalList, filterItems(data.optional || []), 'optional');
      renderList(autoHandledEmailList, filterItems(data.auto_handled || []), 'auto');
      renderList(autoHandledFeedbackList, filterItems(data.auto_handled_feedback || []), 'auto');
    } catch (err) {
      console.warn('dashboard data fetch failed', err);
    }
  }

  updateActionOnlyHint();

  function renderTicketCards(items) {
    if (!ticketResults) return;
    ticketResults.innerHTML = '';
    if (!items || !items.length) {
      ticketResults.innerHTML =
        '<div class="rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-300">No tickets found for this filter.</div>';
      return;
    }
    items.forEach((t) => {
      const created = t.created_at ? new Date(t.created_at).toLocaleString() : '';
      const dueAt = t.due_at ? new Date(t.due_at).toLocaleString() : '';
      const breachSoon = t.due_at && Date.parse(t.due_at) < Date.now() + 60 * 60 * 1000;
      const ticketId = t.id || '';
      const ticketIdDisplay = ticketId
        ? `<span class="text-[11px] text-slate-400 font-mono">ID: ${ticketId}</span>`
        : '';
      const threadLink = t.provider_thread_url
        ? `<a class="text-indigo-300 hover:text-indigo-200 text-[11px]" href="${t.provider_thread_url}" target="_blank" rel="noreferrer">Open source</a>`
        : '';
      const lastQuestion = t.last_question
        ? `<div class="text-[11px] text-slate-400 mt-1"><span class="text-slate-500">Last question:</span> ${t.last_question}</div>`
        : '';
      const summaryText = (t.summary || "").trim();
      const bodyText = (t.body_preview || "").trim();
      const summary =
        summaryText && summaryText !== bodyText
          ? `<div class="text-[11px] text-slate-300 mt-1">${summaryText}</div>`
          : '';
      const bodyPreview = bodyText
        ? `<div class="text-[11px] text-slate-400 mt-1 line-clamp-3">${bodyText}</div>`
        : '';
      const decisionType = t.decision_type ? `<div class="text-[11px] text-slate-400">Decision: ${t.decision_type}</div>` : '';
      const decisionOutcome = t.decision_outcome ? `<div class="text-[11px] text-slate-400">Outcome: ${t.decision_outcome}</div>` : '';
      const confidence =
        typeof t.confidence === 'number'
          ? `<div class="text-[11px] text-slate-400">Confidence: ${Math.round(t.confidence * 100)}%</div>`
          : t.confidence
          ? `<div class="text-[11px] text-slate-400">Confidence: —</div>`
          : '';
      const owner = t.owner ? `<div class="text-[11px] text-slate-400">Owner: ${t.owner}</div>` : '';
      const assignedTo = t.assigned_to ? `<div class="text-[11px] text-slate-400">Assigned to: ${t.assigned_to}</div>` : '';
      const team = t.team ? `<div class="text-[11px] text-slate-400">Team: ${t.team}</div>` : '';
      const auditTrail = Array.isArray(t.decision_trace) && t.decision_trace.length
        ? `<div class="text-[11px] text-slate-400">Audit trail: ${t.decision_trace.join(', ')}</div>`
        : '';
      const aiReason = t.ai_reason ? `<div class="text-[11px] text-slate-400">Why: ${t.ai_reason}</div>` : '';
      const risk = t.risk_flag ? '<span class="ml-1 px-2 py-[2px] rounded-full bg-amber-500/10 text-amber-200 text-[10px]">risk</span>' : '';
      const card = document.createElement('div');
      card.className = 'rounded-xl border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200';
      card.innerHTML = `
        <div class="flex items-center justify-between mb-1">
          <div class="flex flex-col">
            <span class="font-semibold text-slate-100">${t.subject || 'Ticket'} ${risk}</span>
            ${ticketIdDisplay}
          </div>
          <span class="text-[11px] text-slate-400">${created}</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><span class="text-slate-400">Use case:</span> ${t.use_case || 'support'}</div>
          <div><span class="text-slate-400">Channel:</span> ${t.channel || 'email'}</div>
          <div><span class="text-slate-400">Priority:</span> ${t.priority || '-'}</div>
          <div><span class="text-slate-400">Risk:</span> ${t.risk_flag ? 'flagged' : 'none'}</div>
          <div><span class="text-slate-400">Due:</span> ${dueAt || 'n/a'} ${breachSoon ? '<span class="ml-1 px-2 py-[2px] rounded-full bg-rose-500/10 text-rose-200 text-[10px]">breach soon</span>' : ''}</div>
          <div>${threadLink}</div>
        </div>
        ${decisionType}
        ${decisionOutcome}
        ${confidence}
        ${team}
        ${owner}
        ${assignedTo}
        ${aiReason}
        ${auditTrail}
        ${bodyPreview}
        ${summary}
        ${lastQuestion}
        <div class="flex items-center gap-2 mt-2">
          <button class="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px]" data-ticket="${t.id}" data-feedback="true">Triage correct</button>
          <button class="px-3 py-1 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-[11px]" data-ticket="${t.id}" data-feedback="false">Needs fix</button>
        </div>
      `;
      ticketResults.appendChild(card);
    });
    ticketResults.querySelectorAll('button[data-feedback]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const ticketId = btn.dataset.ticket;
        const correct = btn.dataset.feedback === 'true';
        btn.disabled = true;
        try {
          let category = null;
          let priority = null;
          let team = null;
          let assignedTo = null;
          if (!correct) {
            const catInput = prompt('Override category? (leave blank to keep current)');
            const priInput = prompt('Override priority? (P1=Urgent, P2=High, P3=Normal, P4=Low; leave blank to keep current)');
            const teamInput = prompt('Assign to team? (e.g., Billing, Engineering, Support)');
            const ownerInput = prompt('Assign to owner/queue?');
            category = catInput && catInput.trim() ? catInput.trim() : null;
            priority = priInput && priInput.trim() ? priInput.trim() : null;
            team = teamInput && teamInput.trim() ? teamInput.trim() : null;
            assignedTo = ownerInput && ownerInput.trim() ? ownerInput.trim() : null;
          }
          const resp = await fetch(`/api/v1/inboxiq/tickets/${ticketId}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ correct, category, priority, team, assigned_to: assignedTo }),
          });
          const data = await resp.json();
          if (!resp.ok) {
            throw new Error(data.error || `Feedback failed (status ${resp.status})`);
          }
          setTicketStatus('success', correct ? 'Marked as correct' : 'Sent for re-triage');
          // Refresh the ticket list so the updated category/assignment shows immediately.
          performTicketSearch();
        } catch (err) {
          setTicketStatus('error', err.message || 'Feedback failed');
        } finally {
          btn.disabled = false;
        }
      });
    });
  }

  async function performTicketSearch(event) {
    if (event) event.preventDefault();
    const params = new URLSearchParams();
    params.set('page_size', '10');
    if (qInput?.value) params.set('q', qInput.value.trim());
    if (statusInput?.value) params.set('status', statusInput.value);
    if (categoryInput?.value) params.set('category', categoryInput.value);
    if (priorityInput?.value) params.set('priority', priorityInput.value);
    if (afterInput?.value) params.set('created_after', afterInput.value);
    if (beforeInput?.value) params.set('created_before', beforeInput.value);

    setTicketStatus('info', 'Loading tickets…');
    try {
      const resp = await fetch(`/api/v1/inboxiq/tickets?${params.toString()}`, {
        credentials: 'include',
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || 'Failed to load tickets');
      }
      renderTicketCards(data.tickets || []);
      setTicketStatus('success', `Loaded ${data.tickets ? data.tickets.length : 0} tickets`);
    } catch (err) {
      setTicketStatus('error', err.message || 'Unable to load tickets');
    }
  }

  if (searchForm) {
    searchForm.addEventListener('submit', performTicketSearch);
  }

  async function submitTestimonial() {
    if (!submitTestimonialBtn) return;
    const message = (testimonialMsg?.value || '').trim();
    const rating = testimonialRating?.value || '5';
    const consent_public = testimonialConsent?.checked || false;
    if (!message) {
      if (testimonialStatus) {
        testimonialStatus.className = 'text-xs rounded-xl border border-rose-400/40 bg-rose-500/10 text-rose-100 px-3 py-2';
        testimonialStatus.textContent = 'Please enter a short testimonial.';
        testimonialStatus.classList.remove('hidden');
      }
      return;
    }
    submitTestimonialBtn.disabled = true;
    try {
      const resp = await fetch('/api/v1/testimonials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ message, rating, consent_public }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        const msg = data.error === 'insufficient_usage'
          ? 'Please use the product a bit more before submitting a testimonial.'
          : (data.error || 'Unable to submit right now.');
        throw new Error(msg);
      }
      if (testimonialStatus) {
        testimonialStatus.className = 'text-xs rounded-xl border border-emerald-400/40 bg-emerald-500/10 text-emerald-100 px-3 py-2';
        testimonialStatus.textContent = 'Thank you! Submitted.';
        testimonialStatus.classList.remove('hidden');
      }
      try {
        await fetch('/api/v1/inboxiq/forms/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            message,
            context: `Rating: ${rating}${consent_public ? ' • Consent to publish' : ''}`,
            form_name: 'testimonial',
            use_case: 'feedback',
          }),
        });
      } catch (err) {
        console.warn('testimonial intake enqueue failed', err);
      }
      if (testimonialMsg) testimonialMsg.value = '';
    } catch (err) {
      if (testimonialStatus) {
        testimonialStatus.className = 'text-xs rounded-xl border border-rose-400/40 bg-rose-500/10 text-rose-100 px-3 py-2';
        testimonialStatus.textContent = err.message || 'Unable to submit testimonial.';
        testimonialStatus.classList.remove('hidden');
      }
    } finally {
      submitTestimonialBtn.disabled = false;
    }
  }

  if (connectGmailBtn) {
    connectGmailBtn.addEventListener('click', () => startConnect('gmail'));
  }
  if (connectOutlookBtn) {
    connectOutlookBtn.addEventListener('click', () => startConnect('outlook'));
  }

  if (pollNowBtn) {
    pollNowBtn.addEventListener('click', async () => {
      if (pollStatus) {
        pollStatus.classList.remove('hidden');
        pollStatus.textContent = 'Polling inbox...';
      }
      const connectionId = getConnectionId();
      const pollUrl = connectionId ? `/api/v1/inboxiq/poll/${connectionId}` : '/api/v1/inboxiq/poll/mine';
      try {
        const resp = await getJSON(pollUrl);
        const contentType = resp.headers.get('content-type') || '';
        const data = contentType.includes('application/json') ? await resp.json() : {};
        if (!resp.ok) {
          const msg = data.error || data.message || `HTTP ${resp.status}`;
          if (pollStatus) pollStatus.textContent = `Error: ${msg}${resp.status === 401 ? ' (please log in again)' : ''}`;
          return;
        }
        if (pollStatus) pollStatus.textContent = 'Poll triggered. Refreshing...';
        if (data.last_poll) applyPollMeta(data.last_poll, data.poll_health);
        await refreshLastPoll();
      } catch (err) {
        if (pollStatus) pollStatus.textContent = `Error: ${err.message}`;
      }
    });
  }
  if (submitTestimonialBtn) {
    submitTestimonialBtn.addEventListener('click', submitTestimonial);
  }

  // Initial data load for dashboard filters/metrics
  loadDashboardData();

  const logoutForm = document.getElementById('logoutForm');
  if (logoutForm) {
    logoutForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const csrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
      try {
        await fetch('/auth/logout', {
          method: 'POST',
          credentials: 'include',
          headers: csrf ? { 'X-CSRF-TOKEN': csrf } : {},
        });
      } finally {
        window.location.href = '/login';
      }
    });
  }

  // User menu toggle (CSP-safe)
  (function () {
    const btn = document.getElementById('userMenuBtn');
    const menu = document.getElementById('userMenu');
    if (!btn || !menu) return;
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      menu.classList.toggle('hidden');
    });
    document.addEventListener('click', (e) => {
      if (menu.classList.contains('hidden')) return;
      if (!menu.contains(e.target) && !btn.contains(e.target)) {
        menu.classList.add('hidden');
      }
    });
  })();
})();
