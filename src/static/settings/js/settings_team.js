(() => {
  const form = document.getElementById('inviteForm');
  const emailInput = document.getElementById('inviteEmail');
  const button = document.getElementById('inviteButton');
  const statusEl = document.getElementById('inviteStatus');
  const linkEl = document.getElementById('activationLink');

  const setStatus = function(type, message) {
    if (!statusEl) return;
    const colorMap = {
      success: 'text-emerald-200 bg-emerald-500/10 border-emerald-500/30',
      error: 'text-rose-200 bg-rose-500/10 border-rose-500/30',
      info: 'text-indigo-200 bg-indigo-500/10 border-indigo-500/30',
    };
    statusEl.className = `mt-4 text-sm px-3 py-3 rounded-xl border ${colorMap[type] || colorMap.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove('hidden');
  };

  const setLink = function(link) {
    if (!linkEl) return;
    if (!link) {
      linkEl.classList.add('hidden');
      linkEl.textContent = '';
      return;
    }
    linkEl.textContent = `Activation link: ${link}`;
    linkEl.classList.remove('hidden');
  };

  const handleInvite = async function(event) {
    event.preventDefault();
    if (!form || !button) return;

    const email = (emailInput?.value || '').trim().toLowerCase();
    if (!email) {
      setStatus('error', 'Email is required.');
      return;
    }

    button.disabled = true;
    button.textContent = 'Sending...';
    setStatus('info', 'Sending invite...');
    setLink('');

    const csrfToken = document.cookie
      .split(';')
      .map((c) => c.trim())
      .find((c) => c.startsWith('csrf_access_token='))
      ?.split('=')[1];

    try {
      const resp = await fetch('/users/invite', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(csrfToken ? { 'X-CSRF-TOKEN': csrfToken } : {}),
        },
        credentials: 'include',
        body: JSON.stringify({ email }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || 'Unable to send invite.');
      }
      setStatus('success', 'Invite sent. The teammate will get an activation email.');
      if (data.activation_link) {
        setLink(data.activation_link);
      }
      form.reset();
    } catch (err) {
      setStatus('error', err.message || 'Unable to send invite.');
    } finally {
      button.disabled = false;
      button.textContent = 'Send invite';
    }
  };

  if (form) form.addEventListener('submit', handleInvite);
})();
