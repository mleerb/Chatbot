export function safeHtml(source: string): string {
  const template = document.createElement('template');
  template.innerHTML = source;
  const allowed = new Set('html head body title style div span p h1 h2 h3 h4 h5 h6 ul ol li dl dt dd table thead tbody tfoot tr th td caption colgroup col pre code blockquote strong em b i u s br hr section article header footer main nav aside figure figcaption details summary small sup sub label button a'.split(' '));
  const attributes = new Set(['class', 'style', 'title', 'lang', 'dir', 'colspan', 'rowspan', 'width', 'height']);
  for (const element of Array.from(template.content.querySelectorAll('*'))) {
    if (!allowed.has(element.tagName.toLowerCase())) { element.remove(); continue; }
    for (const attribute of Array.from(element.attributes)) {
      if (!attributes.has(attribute.name.toLowerCase())) element.removeAttribute(attribute.name);
    }
    if (element.tagName === 'BUTTON') element.setAttribute('disabled', '');
  }
  const policy = document.createElement('meta');
  policy.httpEquiv = 'Content-Security-Policy';
  policy.content = "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";
  return '<!doctype html><html><head>' + policy.outerHTML + '</head><body>' + template.innerHTML + '</body></html>';
}
