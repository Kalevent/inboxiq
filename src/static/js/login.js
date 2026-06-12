(() => {
  const form = document.getElementById('loginForm');
  const button = document.getElementById('loginButton');
  const statusEl = document.getElementById('loginStatus');
  function clearFields() {
    if (form?.email) form.email.value = '';
    if (form?.password) form.password.value = '';
  }
  // Nudge browsers to drop any stale autofill (e.g., removed accounts).
  clearFields();

  function setStatus(type, message) {
    if (!statusEl) return;
    const colorMap = {
      success: 'text-emerald-200 bg-emerald-500/10 border-emerald-500/30',
      error: 'text-rose-200 bg-rose-500/10 border-rose-500/30',
      info: 'text-indigo-200 bg-indigo-500/10 border-indigo-500/30',
    };
    statusEl.className = `mt-4 text-sm px-3 py-3 rounded-xl border ${colorMap[type] || colorMap.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  }

  async function handleLogin(event) {
    event.preventDefault();
    if (!form || !button) return;

    const email = (form.email?.value || '').trim().toLowerCase();
    const password = form.password?.value || '';
    if (!email || !password) {
      setStatus('error', 'Email and password are required.');
      return;
    }

    const payload = { email, password };

    button.disabled = true;
    button.textContent = 'Signing in...';
    setStatus('info', 'Validating your credentials...');

    try {
      const response = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include', // ensure auth cookies are stored
        body: JSON.stringify(payload),
      });
      const data = await response.json();

      if (!response.ok) {
        if (data.error === 'no_account') {
          setStatus('info', 'No account found. Redirecting you to sign up...');
          setTimeout(() => { window.location.href = '/?open_trial=1'; }, 1200);
          return;
        }
        throw new Error(data.error || 'Unable to log in right now.');
      }

      if (data.account_id !== undefined) {
        localStorage.setItem('inboxiqAccountId', data.account_id);
      }
      if (data.user_id !== undefined) {
        localStorage.setItem('inboxiqUserId', data.user_id);
      }

      if (data.passkey_required) {
        setStatus('info', 'A passkey is configured for this account. Please sign in with your passkey.');
        handlePasskeyLogin();
        return;
      }

      if (data.totp_required) {
        _showTotpStep(data.partial_token);
        return;
      }

      if (data.account_id !== undefined) localStorage.setItem('inboxiqAccountId', data.account_id);
      if (data.user_id !== undefined) localStorage.setItem('inboxiqUserId', data.user_id);

      setStatus('success', 'Signed in. Redirecting...');
      window.location.href = '/dashboard';
    } catch (error) {
      setStatus('error', error.message || 'Login failed.');
    } finally {
      button.disabled = false;
      button.textContent = 'Sign in';
    }
  }

  function _showTotpStep(partialToken) {
    const formEl = document.getElementById('loginForm');
    if (!formEl) return;
    formEl.innerHTML = `
      <p class="text-sm text-slate-300 mb-3">Enter the 6-digit code from your authenticator app.</p>
      <div>
        <label for="totpCode" class="text-sm text-slate-200">Authenticator code</label>
        <input id="totpCode" type="text" inputmode="numeric" maxlength="6" autocomplete="one-time-code"
          class="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-400/30 tracking-widest text-center"
          placeholder="000000" />
      </div>
      <button id="totpSubmit" type="button"
        class="w-full inline-flex justify-center items-center gap-2 rounded-xl bg-indigo-500 hover:bg-indigo-400 px-4 py-2.5 text-sm font-semibold text-white transition disabled:opacity-60 disabled:cursor-not-allowed">
        Verify
      </button>`;
    document.getElementById('totpSubmit')?.addEventListener('click', async () => {
      const code = (document.getElementById('totpCode')?.value || '').trim();
      const btn = document.getElementById('totpSubmit');
      if (!code) { setStatus('error', 'Enter the 6-digit code.'); return; }
      if (btn) { btn.disabled = true; btn.textContent = 'Verifying…'; }
      setStatus('info', 'Verifying code…');
      try {
        const resp = await fetch('/auth/2fa/totp/challenge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ partial_token: partialToken, code }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Invalid code.');
        if (data.account_id !== undefined) localStorage.setItem('inboxiqAccountId', data.account_id);
        if (data.user_id !== undefined) localStorage.setItem('inboxiqUserId', data.user_id);
        setStatus('success', 'Signed in. Redirecting…');
        window.location.href = '/dashboard';
      } catch (err) {
        setStatus('error', err.message || 'Verification failed.');
        if (btn) { btn.disabled = false; btn.textContent = 'Verify'; }
      }
    });
    setStatus('info', 'Two-factor authentication required.');
  }

  if (form) {
    form.addEventListener('submit', handleLogin);
  }

  // ── Passkey login ──────────────────────────────────────────────────────
  function b64urlToBuffer(b64) {
    const pad = 4 - (b64.length % 4);
    const padded = b64 + (pad < 4 ? '='.repeat(pad) : '');
    const bin = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(bin, (c) => c.charCodeAt(0)).buffer;
  }

  function bufferToB64url(buf) {
    return btoa(String.fromCharCode(...new Uint8Array(buf)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  }

  async function handlePasskeyLogin() {
    const pkBtn = document.getElementById('passkeyLoginButton');
    if (!window.PublicKeyCredential) {
      setStatus('error', 'Passkeys are not supported in this browser.');
      return;
    }
    if (pkBtn) { pkBtn.disabled = true; pkBtn.textContent = 'Waiting for passkey…'; }
    setStatus('info', 'Requesting passkey challenge…');
    try {
      const email = (form?.email?.value || '').trim().toLowerCase();
      const optResp = await fetch('/auth/passkeys/authenticate/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(email ? { email } : {}),
      });
      const opts = await optResp.json();
      if (!optResp.ok) throw new Error(opts.error || 'Failed to get passkey options.');

      opts.challenge = b64urlToBuffer(opts.challenge);
      if (opts.allowCredentials) {
        opts.allowCredentials = opts.allowCredentials.map((c) => ({
          ...c, id: b64urlToBuffer(c.id),
        }));
      }

      const credential = await navigator.credentials.get({ publicKey: opts });
      const authResp = credential.response;
      const body = {
        id: credential.id,
        rawId: bufferToB64url(credential.rawId),
        type: credential.type,
        response: {
          clientDataJSON: bufferToB64url(authResp.clientDataJSON),
          authenticatorData: bufferToB64url(authResp.authenticatorData),
          signature: bufferToB64url(authResp.signature),
          userHandle: authResp.userHandle ? bufferToB64url(authResp.userHandle) : null,
        },
      };

      const verResp = await fetch('/auth/passkeys/authenticate/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      const data = await verResp.json();
      if (!verResp.ok) throw new Error(data.error || 'Passkey verification failed.');

      if (data.account_id !== undefined) localStorage.setItem('inboxiqAccountId', data.account_id);
      if (data.user_id !== undefined) localStorage.setItem('inboxiqUserId', data.user_id);

      setStatus('success', 'Signed in with passkey. Redirecting…');
      window.location.href = '/dashboard';
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setStatus('error', 'Passkey cancelled or timed out.');
      } else {
        setStatus('error', err.message || 'Passkey login failed.');
      }
    } finally {
      if (pkBtn) { pkBtn.disabled = false; pkBtn.textContent = 'Sign in with passkey'; }
    }
  }

  const passkeyBtn = document.getElementById('passkeyLoginButton');
  if (passkeyBtn) passkeyBtn.addEventListener('click', handlePasskeyLogin);
})();
