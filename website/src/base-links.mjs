// Astro does not add the configured `base` to hand-authored Markdown links, so
// rewrite site-root links (/…) to include the base at build time. Keeps the docs
// site correct when served from the /baldric GitHub Pages subpath.
function walk(node, fn) {
  if (!node || typeof node !== "object") return;
  fn(node);
  if (Array.isArray(node.children)) {
    for (const child of node.children) walk(child, fn);
  }
}

export function baseLinks(options = {}) {
  const raw = options.base || "/";
  const base = raw.endsWith("/") ? raw : `${raw}/`;
  return (tree) => {
    walk(tree, (node) => {
      if (node.type === "link" && typeof node.url === "string") {
        const url = node.url;
        if (url.startsWith("/") && !url.startsWith("//")) {
          node.url = `${base}${url.slice(1)}`;
        }
      }
    });
  };
}
