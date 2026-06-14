/**
 * Shared dark-mode toggle — used across all public pages.
 * Storage key: 'inboxiq_theme' ('light' | 'dark')
 * Applies/removes 'dark' class on <html>.
 * Light mode is the default; dark activates only if user chose it or OS prefers it.
 */
(function () {
  const updateToggleIcons = function(isDark) {
    document.querySelectorAll('.dark-mode-toggle').forEach(function (btn) {
      btn.innerHTML = isDark ? '☀️' : '🌙';
      btn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
    });
  };

  window.toggleDarkMode = function () {
    const isDark = document.documentElement.classList.toggle('dark');
    try { localStorage.setItem('inboxiq_theme', isDark ? 'dark' : 'light'); } catch (e) {}
    updateToggleIcons(isDark);
  };

  // Init: apply saved or OS preference on page load (before DOMContentLoaded to avoid flash)
  let saved;
  try { saved = localStorage.getItem('inboxiq_theme'); } catch (e) {}
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = saved === 'dark' || (!saved && prefersDark);
  if (isDark) document.documentElement.classList.add('dark');

  document.addEventListener('DOMContentLoaded', function () {
    updateToggleIcons(isDark);
  });
})();
