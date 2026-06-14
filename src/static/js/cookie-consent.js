'use strict';

(function initialiseCookieConsent() {
  const cookieName = 'inboxiq_cookie_consent';
  const cookieDurationDays = 365;
  const strings = {
    bannerMessage:
      'We use cookies to understand usage and improve your experience. We do not share your personal data with third parties.',
    acceptLabel: 'Accept',
    rejectLabel: 'Reject',
    buttonLabel: 'Cookie Settings',
    modalTitle: 'Cookie Settings',
    modalDescription: 'Manage your cookie preferences. You can change this anytime.',
    analyticsLabel: 'Analytics Cookies',
    analyticsDescription: 'These help us understand how visitors use the site. We do not share data with third parties.',
    saveLabel: 'Save Settings',
    closeLabel: 'Close'
  };

  const setCookie = function(name, value, days) {
    const expiresDate = new Date();
    expiresDate.setTime(expiresDate.getTime() + days * 24 * 60 * 60 * 1000);
    const expires = `expires=${expiresDate.toUTCString()}`;
    document.cookie = `${name}=${value};${expires};path=/;SameSite=Lax`;
  };

  const getCookie = function(name) {
    const needle = `${name}=`;
    return document.cookie
      .split(';')
      .map((segment) => segment.trim())
      .filter(Boolean)
      .reduce((acc, segment) => {
        if (acc) return acc;
        return segment.startsWith(needle) ? segment.substring(needle.length) : '';
      }, '');
  };

  const deleteCookie = function(name) {
    document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:01 GMT;path=/;SameSite=Lax`;
  };

  const removeCookieBanner = function() {
    const banner = document.getElementById('cookie-consent-banner');
    if (banner) banner.remove();
  };

  const createCookieBanner = function() {
    if (document.getElementById('cookie-consent-banner')) return;

    const banner = document.createElement('div');
    banner.id = 'cookie-consent-banner';
    banner.className = 'cookie-consent-banner';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-live', 'polite');

    const message = document.createElement('p');
    message.className = 'cookie-consent-message';
    message.textContent = strings.bannerMessage;

    const buttons = document.createElement('div');
    buttons.className = 'cookie-consent-buttons';

    const acceptButton = document.createElement('button');
    acceptButton.type = 'button';
    acceptButton.className = 'cookie-btn cookie-btn-accept';
    acceptButton.textContent = strings.acceptLabel;
    acceptButton.addEventListener('click', () => {
      acceptCookies();
      removeCookieBanner();
    });

    const rejectButton = document.createElement('button');
    rejectButton.type = 'button';
    rejectButton.className = 'cookie-btn cookie-btn-reject';
    rejectButton.textContent = strings.rejectLabel;
    rejectButton.addEventListener('click', () => {
      rejectCookies();
      removeCookieBanner();
    });

    buttons.appendChild(acceptButton);
    buttons.appendChild(rejectButton);

    banner.appendChild(message);
    banner.appendChild(buttons);
    document.body.appendChild(banner);
  };

  const createSettingsButton = function() {
    if (document.getElementById('cookie-settings-button')) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'cookie-settings-button';
    button.className = 'cookie-settings-button';
    button.setAttribute('aria-label', strings.buttonLabel);
    button.title = strings.buttonLabel;
    button.textContent = '🍪';

    button.addEventListener('click', () => {
      showCookieSettings();
    });

    document.body.appendChild(button);
  };

  const buildAnalyticsOption = function(checkboxId) {
    const option = document.createElement('div');
    option.className = 'cookie-settings-option';

    const label = document.createElement('label');
    label.setAttribute('for', checkboxId);

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = checkboxId;
    checkbox.checked = getCookie(cookieName) === 'accepted';

    const labelText = document.createElement('span');
    labelText.className = 'cookie-settings-label';
    labelText.textContent = strings.analyticsLabel;

    const description = document.createElement('p');
    description.className = 'cookie-description';
    description.textContent = strings.analyticsDescription;

    label.appendChild(checkbox);
    label.appendChild(labelText);
    option.appendChild(label);
    option.appendChild(description);

    return option;
  };

  const showCookieSettings = function() {
    const existingModal = document.getElementById('cookie-settings-modal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'cookie-settings-modal';
    modal.className = 'cookie-settings-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'cookie-settings-title');

    const content = document.createElement('div');
    content.className = 'cookie-settings-content';

    const title = document.createElement('h4');
    title.id = 'cookie-settings-title';
    title.textContent = strings.modalTitle;

    const description = document.createElement('p');
    description.className = 'cookie-settings-description';
    description.textContent = strings.modalDescription;

    const analyticsOption = buildAnalyticsOption('analytics-cookies-checkbox');

    const buttons = document.createElement('div');
    buttons.className = 'cookie-settings-buttons';

    const saveButton = document.createElement('button');
    saveButton.type = 'button';
    saveButton.id = 'cookie-settings-save';
    saveButton.className = 'cookie-btn cookie-btn-accept';
    saveButton.textContent = strings.saveLabel;

    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.id = 'cookie-settings-close';
    closeButton.className = 'cookie-btn cookie-btn-reject';
    closeButton.textContent = strings.closeLabel;

    saveButton.addEventListener('click', () => {
      const analyticsConsent = content.querySelector('#analytics-cookies-checkbox').checked;
      if (analyticsConsent) {
        acceptCookies();
      } else {
        rejectCookies();
      }
      modal.remove();
    });

    closeButton.addEventListener('click', () => {
      modal.remove();
    });

    modal.addEventListener('click', (event) => {
      if (event.target === modal) modal.remove();
    });

    buttons.appendChild(saveButton);
    buttons.appendChild(closeButton);
    content.appendChild(title);
    content.appendChild(description);
    content.appendChild(analyticsOption);
    content.appendChild(buttons);
    modal.appendChild(content);
    document.body.appendChild(modal);

    saveButton.focus();
  };

  const acceptCookies = function() {
    setCookie(cookieName, 'accepted', cookieDurationDays);
    createSettingsButton();
  };

  const rejectCookies = function() {
    setCookie(cookieName, 'rejected', cookieDurationDays);
    deleteCookie('_ga');
    deleteCookie('_gid');
    createSettingsButton();
  };

  const initialise = function() {
    const consent = getCookie(cookieName);
    if (consent === 'accepted') {
      createSettingsButton();
      return;
    }

    if (consent === 'rejected') {
      createSettingsButton();
      return;
    }

    createCookieBanner();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialise);
  } else {
    initialise();
  }
})();
