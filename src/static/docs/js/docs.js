/**
 * KalEvent MCP Documentation JavaScript
 * Provides interactive functionality for the documentation system
 */

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    initSidebar();
    initTableOfContents();
    initCodeHighlighting();
    initSearch();
    initMobileNav();
    enhanceLinks();
    initScrollSpy();
    initReadingTime();
    initFeedbackForm();
    initTocToggle();
});

function getDocData(key, fallback) {
    const datasetKey = `docs${key.charAt(0).toUpperCase()}${key.slice(1)}`;
    const body = document.body || {};
    return (body.dataset && body.dataset[datasetKey]) || fallback;
}

/**
 * Initialize sidebar functionality
 */
function initSidebar() {
    // Add active class to current page in sidebar
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.docs-nav-link');
    
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath || 
            currentPath.endsWith(link.getAttribute('href'))) {
            link.classList.add('active');
            
            // Expand parent section if in accordion
            const parentSection = link.closest('.docs-nav-section-content');
            if (parentSection && parentSection.style.display === 'none') {
                parentSection.style.display = 'block';
                const toggle = parentSection.previousElementSibling;
                if (toggle && toggle.classList.contains('docs-nav-section-toggle')) {
                    toggle.classList.add('active');
                }
            }
        }
    });
    
    // Add click handlers for section toggles
    const sectionToggles = document.querySelectorAll('.docs-nav-section-toggle');
    sectionToggles.forEach(toggle => {
        toggle.addEventListener('click', function() {
            this.classList.toggle('active');
            const content = this.nextElementSibling;
            
            if (content.style.display === 'block' || content.style.display === '') {
                content.style.display = 'none';
            } else {
                content.style.display = 'block';
            }
        });
    });
}

/**
 * Initialize table of contents
 */
function initTableOfContents() {
    const content = document.querySelector('.docs-document') || document.querySelector('.docs-content');
    const tocContainer = document.querySelector('#table-of-contents');
    const tocContent = document.querySelector('.docs-toc-content');
    if (!content || !tocContainer || !tocContent) {
        return;
    }

    const headings = Array.from(content.querySelectorAll('h1, h2, h3, h4')).filter(
        (heading) => heading.tagName.toLowerCase() !== 'h1'
    );

    if (headings.length === 0) {
        tocContainer.classList.add('is-hidden');
        const toggleButton = document.getElementById('toc-toggle');
        if (toggleButton) {
            toggleButton.classList.add('is-hidden');
        }
        return;
    }

    tocContent.innerHTML = '';
    const tocList = document.createElement('ul');
    tocList.className = 'docs-toc-list';
    const headingIDs = new Set();

    headings.forEach((heading, index) => {
        if (!heading.id) {
            heading.id = `heading-${index}`;
        }
        if (headingIDs.has(heading.id)) {
            return;
        }
        headingIDs.add(heading.id);

        const item = document.createElement('li');
        item.className = `docs-toc-item docs-toc-${heading.tagName.toLowerCase()}`;

        const link = document.createElement('a');
        link.href = `#${heading.id}`;
        link.className = 'docs-toc-link';
        link.textContent = heading.textContent;
        link.addEventListener('click', (event) => {
            event.preventDefault();
            heading.scrollIntoView({ behavior: 'smooth', block: 'start' });
            history.replaceState(null, '', `#${heading.id}`);
        });

        item.appendChild(link);
        tocList.appendChild(item);
    });

    tocContent.appendChild(tocList);

    if (headings.length < 2) {
        tocContainer.classList.add('is-hidden');
        const toggleButton = document.getElementById('toc-toggle');
        if (toggleButton) {
            toggleButton.classList.add('is-hidden');
        }
    }
}

/**
 * Initialize code syntax highlighting
 */
function initCodeHighlighting() {
    // Check if highlight.js is loaded
    if (typeof hljs !== 'undefined') {
        document.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightBlock(block);
        });
    } else {
        // Fallback basic styling for code blocks
        document.querySelectorAll('pre code').forEach((block) => {
            block.classList.add('code-block');
        });
    }
    
    // Add copy button to code blocks
    const copyLabel = getDocData('copyLabel', 'Copy code');
    const copiedLabel = getDocData('copiedLabel', 'Copied!');

    document.querySelectorAll('pre').forEach((pre) => {
        const copyButton = document.createElement('button');
        copyButton.className = 'docs-copy-button';
        copyButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
        copyButton.ariaLabel = copyLabel;
        copyButton.title = copyLabel;
        
        copyButton.addEventListener('click', function() {
            const code = pre.querySelector('code').innerText;
            
            navigator.clipboard.writeText(code).then(() => {
                // Show success state
                copyButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
                copyButton.title = copiedLabel;
                
                // Reset after 2 seconds
                setTimeout(() => {
                    copyButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
                    copyButton.title = copyLabel;
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy text: ', err);
            });
        });
        
        pre.appendChild(copyButton);
    });
}

/**
 * Initialize search functionality using g.search
 */
function initSearch() {
    const searchInput = document.querySelector('.docs-search-input');
    if (!searchInput) return;
    
    // Create a container for search results
    let searchResultsContainer = document.querySelector('.docs-search-results');
    if (!searchResultsContainer) {
        searchResultsContainer = document.createElement('div');
        searchResultsContainer.className = 'docs-search-results';
        searchResultsContainer.style.display = 'none';
        
        // Insert after search input
        const searchDiv = document.querySelector('.docs-search');
        if (searchDiv) {
            searchDiv.appendChild(searchResultsContainer);
        }
    }
    
    // Create the clear button if it doesn't exist
    let clearButton = document.querySelector('.docs-search-clear');
    if (!clearButton) {
        clearButton = document.createElement('button');
        clearButton.className = 'docs-search-clear';
        clearButton.type = 'button';
        clearButton.innerHTML = '×';
        clearButton.style.display = 'none';
        
        // Insert after search input
        const searchDiv = document.querySelector('.docs-search');
        if (searchDiv) {
            searchDiv.appendChild(clearButton);
        }
    }
    
    // Function to perform search
    function performSearch(query) {
        // Hide results if query is empty
        if (!query || query.trim() === '') {
            searchResultsContainer.style.display = 'none';
            clearButton.style.display = 'none';
            return;
        }
        
        // Display clear button
        clearButton.style.display = 'block';
        
        // Access the global search object if available
        if (window.g && window.g.search) {
            try {
                // Perform search using the global search object
                const results = window.g.search.query(query);
                displaySearchResults(results, query);
            } catch (error) {
                console.error('Error using g.search:', error);
                // Fallback to basic search if g.search fails
                fallbackSearch(query);
            }
        } else {
            // If g.search is not available, use fallback search
            fallbackSearch(query);
        }
    }
    
    const emptyTemplate = getDocData('searchEmpty', 'No results found for "%(query)s"');
    const viewAllTemplate = getDocData('searchView', 'View all %(count)s results');

    // Fallback search function for when g.search is not available
    function fallbackSearch(query) {
        // Simple client-side search through h1, h2, h3, and p elements
        const searchableElements = document.querySelectorAll('h1, h2, h3, p');
        const results = [];
        
        searchableElements.forEach(element => {
            const text = element.textContent.toLowerCase();
            if (text.includes(query.toLowerCase())) {
                // Get the section this element belongs to
                let heading = element;
                if (element.tagName.toLowerCase() === 'p') {
                    // For paragraphs, find the nearest heading
                    heading = findNearestHeading(element);
                }
                
                const headingText = heading ? heading.textContent : 'Unnamed Section';
                
                results.push({
                    title: headingText,
                    content: element.textContent,
                    url: window.location.pathname + '#' + (heading ? heading.id : ''),
                    element: element
                });
            }
        });
        
        displaySearchResults(results, query);
    }
    
    // Helper function to find the nearest heading for a paragraph
    function findNearestHeading(element) {
        let currentElement = element.previousElementSibling;
        
        while (currentElement) {
            const tagName = currentElement.tagName.toLowerCase();
            if (tagName === 'h1' || tagName === 'h2' || tagName === 'h3') {
                return currentElement;
            }
            currentElement = currentElement.previousElementSibling;
        }
        
        return null;
    }
    
    // Function to display search results
    function displaySearchResults(results, query) {
        // Clear previous results
        searchResultsContainer.innerHTML = '';
        
        if (results.length === 0) {
            const emptyMessage = emptyTemplate.replace('%(query)s', query);
            searchResultsContainer.innerHTML = `<div class="docs-search-empty">${emptyMessage}</div>`;
            searchResultsContainer.style.display = 'block';
            return;
        }
        
        // Limit to top 5 results for UI cleanliness
        const limitedResults = results.slice(0, 5);
        
        // Create result elements
        const resultsList = document.createElement('ul');
        resultsList.className = 'docs-search-results-list';
        
        limitedResults.forEach(result => {
            const listItem = document.createElement('li');
            listItem.className = 'docs-search-result-item';
            
            const link = document.createElement('a');
            link.href = result.url;
            link.className = 'docs-search-result-link';
            
            const title = document.createElement('div');
            title.className = 'docs-search-result-title';
            title.textContent = result.title;
            
            const content = document.createElement('div');
            content.className = 'docs-search-result-content';
            
            // Create a snippet that highlights the query term
            const lowerContent = result.content.toLowerCase();
            const queryIndex = lowerContent.indexOf(query.toLowerCase());
            
            if (queryIndex !== -1) {
                // Extract a snippet centered around the match
                const snippetStart = Math.max(0, queryIndex - 30);
                const snippetEnd = Math.min(result.content.length, queryIndex + query.length + 30);
                let snippet = result.content.substring(snippetStart, snippetEnd);
                
                if (snippetStart > 0) snippet = '...' + snippet;
                if (snippetEnd < result.content.length) snippet = snippet + '...';
                
                // Highlight the matched query
                const highlightedSnippet = snippet.replace(
                    new RegExp(query, 'gi'),
                    match => `<strong class="docs-search-highlight">${match}</strong>`
                );
                
                content.innerHTML = highlightedSnippet;
            } else {
                // Just use the first part of the content if no match found
                content.textContent = result.content.substring(0, 60) + '...';
            }
            
            link.appendChild(title);
            link.appendChild(content);
            listItem.appendChild(link);
            resultsList.appendChild(listItem);
            
            // Add click handler to navigate to the result
            link.addEventListener('click', function(e) {
                e.preventDefault();
                
                // If it's an anchor link on the current page
                if (result.url.includes('#')) {
                    const targetId = result.url.split('#')[1];
                    const targetElement = document.getElementById(targetId);
                    
                    if (targetElement) {
                        // Scroll to the element
                        targetElement.scrollIntoView({ behavior: 'smooth' });
                        
                        // Clear search and hide results
                        searchInput.value = '';
                        searchResultsContainer.style.display = 'none';
                        clearButton.style.display = 'none';
                        
                        // Highlight the element briefly
                        targetElement.classList.add('docs-search-target');
                        setTimeout(() => {
                            targetElement.classList.remove('docs-search-target');
                        }, 2000);
                    } else {
                        // If target doesn't exist on this page, navigate normally
                        window.location.href = result.url;
                    }
                } else {
                    // Regular navigation
                    window.location.href = result.url;
                }
            });
        });
        
        searchResultsContainer.appendChild(resultsList);
        
        // Show a "View all results" link if there are more than 5 results
        if (results.length > 5) {
            const viewAllLink = document.createElement('a');
            viewAllLink.href = '/docs/search?q=' + encodeURIComponent(query);
            viewAllLink.className = 'docs-search-view-all';
            viewAllLink.textContent = viewAllTemplate.replace('%(count)s', results.length);
            searchResultsContainer.appendChild(viewAllLink);
        }
        
        // Show the results container
        searchResultsContainer.style.display = 'block';
    }
    
    // Listen for input events to provide real-time search
    let debounceTimeout;
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        
        // Clear previous timeout
        clearTimeout(debounceTimeout);
        
        // Set a new timeout to debounce the search
        debounceTimeout = setTimeout(() => {
            performSearch(query);
        }, 300); // 300ms debounce time
    });
    
    // Add form submission handling
    const searchForm = searchInput.closest('form') || searchInput.parentElement;
    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const query = searchInput.value.trim();
            if (query) {
                // Redirect to full search page for form submission
                window.location.href = '/docs/search?q=' + encodeURIComponent(query);
            }
        });
    }
    
    // Clear search when clicking the clear button
    clearButton.addEventListener('click', function() {
        searchInput.value = '';
        searchInput.focus();
        searchResultsContainer.style.display = 'none';
        this.style.display = 'none';
    });
    
    // Close search results when clicking outside
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && 
            !searchResultsContainer.contains(e.target) && 
            !clearButton.contains(e.target)) {
            searchResultsContainer.style.display = 'none';
        }
    });
    
}

/**
 * Initialize mobile navigation
 */
function initMobileNav() {
    const menuToggle = document.querySelector('.docs-sidebar-toggle');
    if (!menuToggle) return;
    
    menuToggle.addEventListener('click', function() {
        const sidebar = document.querySelector('.docs-sidebar');
        sidebar.classList.toggle('open');
        
        // Add overlay when sidebar is open
        let overlay = document.querySelector('.docs-sidebar-overlay');
        
        if (sidebar.classList.contains('open')) {
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.className = 'docs-sidebar-overlay';
                document.body.appendChild(overlay);
                
                overlay.addEventListener('click', function() {
                    sidebar.classList.remove('open');
                    this.remove();
                });
            }
        } else if (overlay) {
            overlay.remove();
        }
    });
}

/**
 * Enhance document links to work within the documentation system
 */
function enhanceLinks() {
    document.querySelectorAll('.docs-content a, .docs-document a').forEach(link => {
        const href = link.getAttribute('href');
        
        // Only modify relative links that end with .md
        if (href && href.endsWith('.md') && !href.startsWith('http')) {
            // Remove .md extension for internal navigation
            const newHref = href.replace('.md', '');
            link.setAttribute('href', newHref);
        }
        
        // Open external links in new tab
        if (href && (href.startsWith('http://') || href.startsWith('https://'))) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
            
            // Add external link icon
            if (!link.querySelector('.external-link-icon')) {
                const icon = document.createElement('span');
                icon.className = 'external-link-icon';
                icon.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>';
                link.appendChild(icon);
            }
        }
    });
}

/**
 * Initialize scrollspy for table of contents
 */
function initScrollSpy() {
    const tocLinks = document.querySelectorAll('.docs-toc-link');
    if (tocLinks.length === 0) return;
    
    const scope = document.querySelector('.docs-document') || document;
    const headingElements = Array.from(scope.querySelectorAll('h2, h3, h4')).filter(el => el.id);
    
    const observerOptions = {
        root: null,
        rootMargin: '0px 0px -80% 0px',
        threshold: 0
    };
    
    const headingObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const id = entry.target.getAttribute('id');
            const tocLink = document.querySelector(`.docs-toc-link[href="#${id}"]`);
            
            if (tocLink) {
                if (entry.isIntersecting) {
                    // Remove active class from all links
                    tocLinks.forEach(link => link.classList.remove('active'));
                    // Add active class to current link
                    tocLink.classList.add('active');
                }
            }
        });
    }, observerOptions);
    
    headingElements.forEach(heading => {
        headingObserver.observe(heading);
    });
    
    // Update active link on scroll
    window.addEventListener('scroll', function() {
        // Find the heading closest to the top of the viewport
        let closestHeading = null;
        let closestDistance = Number.MAX_VALUE;
        
        headingElements.forEach(heading => {
            const rect = heading.getBoundingClientRect();
            const distance = Math.abs(rect.top);
            
            if (distance < closestDistance) {
                closestDistance = distance;
                closestHeading = heading;
            }
        });
        
        if (closestHeading) {
            const id = closestHeading.getAttribute('id');
            const activeLink = document.querySelector(`.docs-toc-link[href="#${id}"]`);
            
            if (activeLink) {
                tocLinks.forEach(link => link.classList.remove('active'));
                activeLink.classList.add('active');
            }
        }
    }, { passive: true });
}

function initReadingTime() {
    const container = document.querySelector('.docs-document');
    const readingElement = document.getElementById('reading-time');
    if (!container || !readingElement) {
        return;
    }
    const text = container.textContent || container.innerText || '';
    const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
    const minutes = Math.max(1, Math.ceil(wordCount / 200));
    const label = getDocData('readingLabel', 'min read');
    readingElement.textContent = `${minutes} ${label}`;
}

function initFeedbackForm() {
    const yesButton = document.getElementById('feedback-yes');
    const noButton = document.getElementById('feedback-no');
    const form = document.querySelector('.docs-feedback-form');
    const thanks = document.querySelector('.docs-feedback-thanks');
    const submit = document.querySelector('.docs-feedback-submit');
    if (!yesButton || !noButton || !form || !thanks) {
        return;
    }

    const showThanks = () => {
        form.classList.add('is-hidden');
        thanks.classList.remove('is-hidden');
    };

    yesButton.addEventListener('click', () => {
        yesButton.classList.add('active');
        noButton.classList.remove('active');
        showThanks();
    });

    noButton.addEventListener('click', () => {
        noButton.classList.add('active');
        yesButton.classList.remove('active');
        form.classList.remove('is-hidden');
        thanks.classList.add('is-hidden');
    });

    if (submit) {
        submit.addEventListener('click', () => {
            showThanks();
        });
    }
}

function initTocToggle() {
    const toggle = document.getElementById('toc-toggle');
    const toc = document.getElementById('table-of-contents');
    if (!toggle || !toc || toc.classList.contains('is-hidden')) {
        return;
    }

    const showLabel = getDocData('tocShow', 'Show Table of Contents');
    const hideLabel = getDocData('tocHide', 'Hide Table of Contents');

    const updateLabel = () => {
        const labelEl = toggle.querySelector('span');
        if (!labelEl) {
            return;
        }
        labelEl.textContent = toc.classList.contains('toc-hidden') ? showLabel : hideLabel;
    };

    toggle.addEventListener('click', () => {
        toc.classList.toggle('toc-hidden');
        updateLabel();
    });

    if (window.innerWidth < 1024) {
        toc.classList.add('toc-hidden');
    }
    updateLabel();
}
