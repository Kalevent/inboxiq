// Build a right-hand table of contents from h2/h3 headings.
(function() {
  const content = document.getElementById('docsContent');
  if (!content) return;
  const headings = Array.from(content.querySelectorAll('h2, h3'));
  if (!headings.length) return;

  const list = document.createElement('ul');
  headings.forEach((h, idx) => {
    if (!h.id) {
      h.id = 'section-' + idx;
    }
    const li = document.createElement('li');
    li.className = h.tagName === 'H2' ? 'docs-toc-item' : 'docs-toc-subitem';
    const a = document.createElement('a');
    a.href = '#' + h.id;
    a.textContent = h.textContent;
    li.appendChild(a);
    list.appendChild(li);
  });

  const target = document.getElementById('docsTocNav');
  if (target) {
    target.appendChild(list);
  }
})();
