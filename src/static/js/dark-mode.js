/**
 * Shared dark-mode toggle — used across all public pages.
 * Storage key: 'inboxiq_theme' ('light' | 'dark')
 * Applies/removes 'dark' class on <html>.
 * Light mode is the default; dark activates only if user chose it or OS prefers it.
 */
(function () {
  function updateToggleIcons(isDark) {
    document.querySelectorAll('.dark-mode-toggle').forEach(function (btn) {
      btn.innerHTML = isDark ? '☀️' : '🌙';
      btn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
    });
  }

  window.toggleDarkMode = function () {
    var isDark = document.documentElement.classList.toggle('dark');
    try { localStorage.setItem('inboxiq_theme', isDark ? 'dark' : 'light'); } catch (e) {}
    updateToggleIcons(isDark);
  };

  // Init: apply saved or OS preference on page load (before DOMContentLoaded to avoid flash)
  var saved;
  try { saved = localStorage.getItem('inboxiq_theme'); } catch (e) {}
  var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  var isDark = saved === 'dark' || (!saved && prefersDark);
  if (isDark) document.documentElement.classList.add('dark');

  document.addEventListener('DOMContentLoaded', function () {
    updateToggleIcons(isDark);
  });
})();
