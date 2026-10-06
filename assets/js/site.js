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
  const headings = [...article.querySelectorAll('h2')];
  if (headings.length < 3) return;
  const contents = document.createElement('details');
  contents.className = 'page-contents';
  const summary = document.createElement('summary');
  summary.textContent = 'On this page';
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
