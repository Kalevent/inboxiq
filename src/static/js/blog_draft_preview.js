(() => {
  const onReady = (fn) => {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  };

  onReady(() => {
    const btn = document.getElementById('copyFeedback');
    const status = document.getElementById('fbStatus');
    const jsonPreview = document.getElementById('fbJsonPreview');
    if (!btn || !jsonPreview) return;

    const ids = ['fbTitle', 'fbSubtitle', 'fbAudience', 'fbCta', 'fbTags', 'fbNotes'];
    const getVal = (id) => (document.getElementById(id)?.value || '').trim();
    const show = (msg) => {
      if (status) status.textContent = msg;
    };

    const buildPayload = () => ({
      title: getVal('fbTitle'),
      subtitle: getVal('fbSubtitle'),
      audience: getVal('fbAudience'),
      cta: getVal('fbCta'),
      tags: getVal('fbTags')
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
      notes: getVal('fbNotes'),
      draft_id: jsonPreview.dataset.draftId || '',
      status: jsonPreview.dataset.draftStatus || 'draft',
      slug: jsonPreview.dataset.slug || '',
    });

    const updatePreview = () => {
      const text = JSON.stringify(buildPayload(), null, 2);
      jsonPreview.value = text;
      return text;
    };

    const copyUsingTextarea = async (text) => {
      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(text);
          return true;
        } catch (e) {
          // continue to fallback
        }
      }
      const helper = document.createElement('textarea');
      helper.value = text;
      helper.setAttribute('readonly', '');
      helper.style.position = 'absolute';
      helper.style.left = '-9999px';
      document.body.appendChild(helper);
      helper.focus();
      helper.select();
      helper.setSelectionRange(0, helper.value.length);
      let ok = false;
      try {
        ok = document.execCommand('copy');
      } catch (e) {
        ok = false;
      }
      document.body.removeChild(helper);
      return ok;
    };

    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('input', updatePreview);
      el.addEventListener('change', updatePreview);
      el.addEventListener('blur', updatePreview);
    });

    // initial sync
    updatePreview();

    btn.addEventListener('click', async () => {
      const text = updatePreview();
      const ok = await copyUsingTextarea(text);
      show(ok ? 'Feedback copied to clipboard.' : 'Unable to copy; please copy manually (textarea above).');
    });
  });
})();
