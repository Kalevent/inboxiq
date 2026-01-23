(function () {
    const body = document.body;
    if (!body || !body.dataset) {
        return;
    }

    const analyticsId = body.dataset.analyticsId;
    if (!analyticsId) {
        return;
    }

    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () {
        window.dataLayer.push(arguments);
    };

    window.gtag('js', new Date());
    window.gtag('config', analyticsId);
})();
