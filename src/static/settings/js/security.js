(() => {
  const b64ToArrayBuffer = (b64) => {
    const pad = '='.repeat((4 - (b64.length % 4)) % 4);
    const base64 = (b64 + pad).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray.buffer;
  };

  const arrayBufferToB64 = (buffer) => {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    bytes.forEach((b) => (binary += String.fromCharCode(b)));
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  };

  const passkeyButton = document.getElementById('registerPasskey');
  const passkeyStatus = document.getElementById('passkeyStatus');
  const passkeyList = document.getElementById('passkeyList');

  function setPasskeyStatus(type, message) {
    if (!passkeyStatus) return;
    const colors = {
      success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-500/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-500/40 bg-indigo-500/10 text-indigo-100',
    };
    passkeyStatus.className = `text-xs px-3 py-2 rounded-xl border ${colors[type] || colors.info}`;
    passkeyStatus.textContent = message;
    passkeyStatus.classList.remove('hidden');
  }

  async function refreshPasskeyList() {
    if (!passkeyList) return;
    try {
      const resp = await fetch('/auth/passkeys/list', { credentials: 'include' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Unable to load passkeys');
      passkeyList.innerHTML = '';
      passkeyList.classList.remove('hidden');
      (data.passkeys || []).forEach((p) => {
        const li = document.createElement('li');
        li.className = 'flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm';
        li.dataset.passkeyId = p.id;
        li.innerHTML = `<span class="text-slate-100">${p.label || 'Passkey'}</span><div class="flex items-center gap-3"><span class="text-xs text-slate-500">${p.created_at || ''}</span><button class="text-xs text-rose-400 hover:text-rose-300 font-medium" data-delete-passkey="${p.id}">Delete</button></div>`;
        passkeyList.appendChild(li);
      });
      passkeyList.querySelectorAll('[data-delete-passkey]').forEach((btn) => {
        btn.addEventListener('click', () => deletePasskey(btn.dataset.deletePasskey));
      });
    } catch (err) {
      setPasskeyStatus('error', err.message || 'Unable to refresh passkeys');
    }
  }

  async function deletePasskey(id) {
    if (!confirm('Remove this passkey? You will need your password or another passkey to sign in.')) return;
    try {
      const resp = await fetch('/auth/passkeys/delete', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(csrf() ? { 'X-CSRF-TOKEN': csrf() } : {}),
        },
        body: JSON.stringify({ id }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Failed to delete passkey');
      setPasskeyStatus('success', 'Passkey removed.');
      refreshPasskeyList();
    } catch (err) {
      setPasskeyStatus('error', err.message || 'Unable to delete passkey');
    }
  }

  async function registerPasskey() {
    if (!window.PublicKeyCredential) {
      setPasskeyStatus('error', 'Passkeys not supported in this browser.');
      return;
    }
    setPasskeyStatus('info', 'Requesting passkey options...');
    const optionsResp = await fetch('/auth/passkeys/registration/options', {
      method: 'POST',
      credentials: 'include',
      headers: csrf() ? { 'X-CSRF-TOKEN': csrf() } : {},
    });
    const optsJson = await optionsResp.json();
    if (!optionsResp.ok) {
      setPasskeyStatus('error', optsJson.error || 'Failed to get options');
      return;
    }
    const publicKey = { ...optsJson, challenge: b64ToArrayBuffer(optsJson.challenge) };
    publicKey.user.id = new TextEncoder().encode(publicKey.user.id);
    if (publicKey.excludeCredentials) {
      publicKey.excludeCredentials = publicKey.excludeCredentials.map((cred) => ({
        ...cred,
        id: b64ToArrayBuffer(cred.id),
      }));
    }
    const credential = await navigator.credentials.create({ publicKey });
    const attResp = credential.response;
    const registrationResponse = {
      id: credential.id,
      rawId: arrayBufferToB64(credential.rawId),
      type: credential.type,
      response: {
        attestationObject: arrayBufferToB64(attResp.attestationObject),
        clientDataJSON: arrayBufferToB64(attResp.clientDataJSON),
        transports: attResp.getTransports ? attResp.getTransports() : [],
      },
    };
    const verifyResp = await fetch('/auth/passkeys/registration/verify', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(csrf() ? { 'X-CSRF-TOKEN': csrf() } : {}),
      },
      body: JSON.stringify(registrationResponse),
    });
    const verifyJson = await verifyResp.json();
    if (!verifyResp.ok) {
      setPasskeyStatus('error', verifyJson.error || 'Failed to register passkey');
      return;
    }
    setPasskeyStatus('success', 'Passkey registered.');
    refreshPasskeyList();
    await _notifyMfaCompleteIfRequired();
  }

  if (passkeyButton) {
    passkeyButton.addEventListener('click', () => {
      registerPasskey().catch((err) => setPasskeyStatus('error', err.message || 'Passkey error'));
    });
  }

  // TOTP flows
  const totpStartBtn = document.getElementById('totpStart');
  const totpVerifyBtn = document.getElementById('totpVerify');
  const totpDisableBtn = document.getElementById('totpDisable');
  const totpSecretEl = document.getElementById('totpSecret');
  const totpDeviceIdEl = document.getElementById('totpDeviceId');
  const totpUriEl = document.getElementById('totpUri');
  const totpLinkEl = document.getElementById('totpLink');
  const totpCopyEl = document.getElementById('totpCopy');
  const totpCodeInput = document.getElementById('totpCode');
  const totpStatus = document.getElementById('totpStatus');

  function setTotpStatus(type, message) {
    if (!totpStatus) return;
    const colors = {
      success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100',
      error: 'border-rose-500/40 bg-rose-500/10 text-rose-100',
      info: 'border-indigo-500/40 bg-indigo-500/10 text-indigo-100',
    };
    totpStatus.className = `text-xs px-3 py-2 rounded-xl border ${colors[type] || colors.info}`;
    totpStatus.textContent = message;
    totpStatus.classList.remove('hidden');
  }

  async function startTotp() {
    const resp = await fetch('/auth/2fa/totp/start', {
      method: 'POST',
      credentials: 'include',
      headers: csrf() ? { 'X-CSRF-TOKEN': csrf() } : {},
    });
    const data = await resp.json();
    if (!resp.ok) {
      setTotpStatus('error', data.error || 'Unable to start TOTP');
      return;
    }
    if (totpSecretEl) totpSecretEl.textContent = data.secret;
    if (totpDeviceIdEl) totpDeviceIdEl.value = data.device_id;
    if (totpUriEl) totpUriEl.value = data.otpauth_url || '';
    if (totpLinkEl && data.otpauth_url) totpLinkEl.href = data.otpauth_url;
    setTotpStatus('info', 'Enter the code from your authenticator app and verify.');
  }

  async function verifyTotp() {
    const code = totpCodeInput?.value?.trim();
    const deviceId = totpDeviceIdEl?.value;
    if (!code || !deviceId) {
      setTotpStatus('error', 'Start setup and enter the code.');
      return;
    }
    const resp = await fetch('/auth/2fa/totp/verify', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(csrf() ? { 'X-CSRF-TOKEN': csrf() } : {}),
      },
      body: JSON.stringify({ device_id: deviceId, code }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      setTotpStatus('error', data.error || 'Invalid code');
      return;
    }
    setTotpStatus('success', '2FA enabled.');
    await _notifyMfaCompleteIfRequired();
  }

  async function disableTotp() {
    const resp = await fetch('/auth/2fa/totp/disable', {
      method: 'POST',
      credentials: 'include',
      headers: csrf() ? { 'X-CSRF-TOKEN': csrf() } : {},
    });
    const data = await resp.json();
    if (!resp.ok) {
      setTotpStatus('error', data.error || 'Unable to disable 2FA');
      return;
    }
    setTotpStatus('success', '2FA disabled.');
    if (totpSecretEl) totpSecretEl.textContent = '';
    if (totpDeviceIdEl) totpDeviceIdEl.value = '';
    if (totpCodeInput) totpCodeInput.value = '';
  }

  // MFA setup completion — called after passkey or TOTP is registered when redirected from activation
  const _mfaRequired = new URLSearchParams(window.location.search).get('mfa_required') === '1';

  if (_mfaRequired) {
    const banner = document.createElement('div');
    banner.className = 'mb-6 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100';
    banner.textContent = 'Security setup required — please configure TOTP 2FA or register a passkey before accessing your workspace.';
    document.querySelector('.settings-content, main, [data-settings-content]')?.prepend(banner)
      || document.body.prepend(banner);
  }

  async function _notifyMfaCompleteIfRequired() {
    if (!_mfaRequired) return;
    try {
      await fetch('/auth/mfa/setup-complete', {
        method: 'POST',
        credentials: 'include',
        headers: csrf() ? { 'X-CSRF-TOKEN': csrf() } : {},
      });
    } catch (_) { /* non-blocking */ }
    window.location.href = '/dashboard';
  }

  if (totpStartBtn) totpStartBtn.addEventListener('click', () => startTotp().catch((err) => setTotpStatus('error', err.message || 'Error')));
  if (totpVerifyBtn) totpVerifyBtn.addEventListener('click', () => verifyTotp().catch((err) => setTotpStatus('error', err.message || 'Error')));
  if (totpDisableBtn) totpDisableBtn.addEventListener('click', () => disableTotp().catch((err) => setTotpStatus('error', err.message || 'Error')));
  if (totpCopyEl) {
    totpCopyEl.addEventListener('click', async () => {
      const secret = totpSecretEl?.textContent?.trim();
      if (!secret) return;
      try {
        await navigator.clipboard.writeText(secret);
        setTotpStatus('success', 'Secret copied.');
      } catch (err) {
        setTotpStatus('error', 'Unable to copy secret.');
      }
    });
  }
})();
  const getCookie = (name) => {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : '';
  };
  const csrf = () => getCookie('csrf_access_token') || getCookie('csrf_refresh_token') || '';
