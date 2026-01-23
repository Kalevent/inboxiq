document.addEventListener('DOMContentLoaded', () => {
    const clearButton = document.getElementById('search-clear');
    const searchInput = document.getElementById('search-query');
    if (clearButton && searchInput) {
        clearButton.addEventListener('click', () => {
            searchInput.value = '';
            searchInput.focus();
        });
    }

    const resultsContainer = document.querySelector('[data-search-query]');
    const query = resultsContainer ? resultsContainer.dataset.searchQuery : '';
    if (!query) {
        return;
    }

    const regex = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    document.querySelectorAll('.docs-search-result-snippet').forEach((snippet) => {
        snippet.innerHTML = snippet.textContent.replace(regex, (match) => `<mark>${match}</mark>`);
    });
});
