// Enhance article navigation. All article text and links work without JavaScript.
(() => {
  const article = document.querySelector('.prose');
  if (!article) return;
  article.querySelectorAll('table').forEach(table => {
    const wrapper = document.createElement('div');
    wrapper.className = 'table-scroll';
    wrapper.tabIndex = 0;
    wrapper.setAttribute('role', 'region');
    wrapper.setAttribute('aria-label', 'Article table; scroll horizontally if needed');
    table.before(wrapper);
    wrapper.append(table);
  });
  // Fold long code blocks: show the first lines, with a button to expand. The full code stays in the page.
  const FOLD_AT = 24;
  article.querySelectorAll('pre').forEach(pre => {
    const lines = pre.textContent.replace(/\n$/, '').split('\n').length;
    if (lines <= FOLD_AT) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'code-fold is-folded';
    pre.before(wrapper);
    wrapper.append(pre);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'code-toggle';
    button.setAttribute('aria-expanded', 'false');
    const label = () => {
      const folded = wrapper.classList.contains('is-folded');
      button.textContent = folded ? `Show all ${lines} lines` : 'Collapse';
      button.setAttribute('aria-expanded', String(!folded));
    };
    button.addEventListener('click', () => {
      wrapper.classList.toggle('is-folded');
      label();
      const top = wrapper.getBoundingClientRect().top;
      if (wrapper.classList.contains('is-folded') && top < 0) wrapper.scrollIntoView({ block: 'start' });
    });
    label();
    wrapper.append(button);
  });
  const headings = [...article.querySelectorAll('h2')];
  if (headings.length < 3) return;
  const contents = document.createElement('details');
  contents.className = 'page-contents';
  const summary = document.createElement('summary');
  summary.textContent = 'Contents';
  const list = document.createElement('ol');
  headings.forEach((heading, index) => {
    if (!heading.id) heading.id = `section-${index + 1}`;
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent;
    item.append(link);
    list.append(item);
  });
  contents.append(summary, list);
  const title = article.querySelector('h1');
  if (title) title.after(contents);
  else article.prepend(contents);
})();
