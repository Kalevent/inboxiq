(() => {
  const state = window.RolesPage || {};
  const roles = state.roles || [];
  const roleMap = Object.fromEntries((roles || []).map((r) => [r.key, r]));
  const csrfToken = state.csrfToken || "";
  const selects = Array.from(document.querySelectorAll("[data-role-select]"));
  const statusEl = document.getElementById("roleStatus");

  const setStatus = function(type, message) {
    if (!statusEl) return;
    const colors = {
      success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100",
      error: "border-rose-500/40 bg-rose-500/10 text-rose-100",
      info: "border-indigo-500/40 bg-indigo-500/10 text-indigo-100",
    };
    statusEl.className = `text-xs px-3 py-2 rounded-xl border ${colors[type] || colors.info}`;
    statusEl.textContent = message;
    statusEl.classList.remove("hidden");
  };

  const updateRole = async function(selectEl) {
    const userId = selectEl?.dataset?.userId;
    const email = selectEl?.dataset?.email;
    const previous = selectEl?.dataset?.currentRole || selectEl?.value;
    const nextRole = selectEl?.value;
    if (!userId || !nextRole) return;

    selectEl.disabled = true;
    setStatus("info", `Updating ${email} to ${roleMap[nextRole]?.label || nextRole}...`);
    try {
      const resp = await fetch("/api/roles/assignments", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-TOKEN": csrfToken } : {}),
        },
        body: JSON.stringify({ user_id: userId, role: nextRole }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || "Unable to update role");
      }
      selectEl.dataset.currentRole = nextRole;
      setStatus("success", `${email} is now ${roleMap[nextRole]?.label || nextRole}.`);
    } catch (err) {
      selectEl.value = previous;
      setStatus("error", err.message || "Unable to update role.");
    } finally {
      selectEl.disabled = false;
    }
  };

  selects.forEach((selectEl) => {
    selectEl.addEventListener("change", () => updateRole(selectEl));
  });
})();
