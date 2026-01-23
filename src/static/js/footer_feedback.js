document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("footerFeedbackForm");
  const modal = document.getElementById("footerFeedbackModal");
  const openBtn = document.getElementById("openFeedbackModal");
  const closeBtn = document.getElementById("closeFeedbackModal");
  const inlineStatus = document.getElementById("footerFeedbackStatusLink");
  if (!form || !modal || !openBtn || !closeBtn) return;

  const messageEl = document.getElementById("footerFeedbackMessage");
  const contextEl = document.getElementById("footerFeedbackContext");
  const ratingEl = document.getElementById("footerFeedbackRating");
  const statusEl = document.getElementById("footerFeedbackStatus");
  const submitBtn = document.getElementById("footerFeedbackSubmit");

  const showModal = () => {
    // Ensure modal is at document body level so it sits above all content.
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    modal.classList.remove("hidden");
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  };
  const hideModal = () => {
    modal.classList.add("hidden");
    modal.style.display = "none";
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  };

  openBtn.addEventListener("click", () => {
    inlineStatus?.classList.add("hidden");
    showModal();
    // Keep focus near the textarea for quick input.
    setTimeout(() => {
      messageEl?.focus();
    }, 50);
  });
  closeBtn.addEventListener("click", hideModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) hideModal();
  });

  const showStatus = (text, tone = "muted", target = "modal") => {
    const el = target === "link" ? inlineStatus : statusEl;
    if (!el) return;
    el.classList.remove("hidden");
    const base = "text-xs rounded-lg px-3 py-2";
    const palette =
      tone === "error"
        ? "border border-rose-400/40 bg-rose-500/10 text-rose-100"
        : tone === "success"
          ? "border border-emerald-400/40 bg-emerald-500/10 text-emerald-100"
          : "text-slate-300";
    el.className = `${base} ${palette}`;
    el.textContent = text;
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = (messageEl?.value || "").trim();
    const context = (contextEl?.value || "").trim();
    const urgency = Number(ratingEl?.value || 3) || 3;

    if (!message) {
      showStatus("Please add a short note before sending.", "error");
      return;
    }

    const payload = {
      message,
      context: context || null,
      urgency,
    };

    try {
      submitBtn && (submitBtn.disabled = true);
      showStatus("Sending…");

      const res = await fetch("/api/v1/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || "Unable to send feedback right now.");
      }

      showStatus("Thanks—got it! We’ll triage this with the rest of InboxIQ.", "success");
      showStatus("Thanks—received.", "success", "link");
      if (messageEl) messageEl.value = "";
      if (contextEl) contextEl.value = "";
      if (ratingEl) ratingEl.value = "3";
      setTimeout(() => hideModal(), 600);
    } catch (err) {
      showStatus(err.message || "Unable to send feedback right now.", "error");
      showStatus("Send failed", "error", "link");
    } finally {
      submitBtn && (submitBtn.disabled = false);
    }
  });
});
