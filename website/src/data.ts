import { readFileSync } from "node:fs";
import { parse as yaml } from "yaml";
import { parse as toml } from "smol-toml";

// The site is served from the /baldric subpath on GitHub Pages, so internal
// links and path comparisons must carry that base prefix.
export const base = import.meta.env.BASE_URL;

export function withBase(path: string): string {
  if (/^(https?:|mailto:|tel:|#|\/\/)/i.test(path)) return path;
  return path.startsWith("/") ? `${base}${path.slice(1)}` : `${base}${path}`;
}

export function stripBase(path: string): string {
  return path.startsWith(base) ? `/${path.slice(base.length)}` : path;
}

export const site = {
  title: "Baldric",
  description: "An educational Python project for learning how coding agents are built.",
  githubUrl: "https://github.com/Ember452/baldric",
  discordUrl: "https://github.com/Ember452/baldric/discussions",
  editRepoUrl: "https://github.com/Ember452/baldric/edit/main/website/content",
  githubRepo: "Ember452/baldric",
};
export const version = (
  toml(readFileSync("../pyproject.toml", "utf8")).project as { version: string }
).version;
export interface Link {
  label: string;
  path: string;
}
export interface Group {
  label: string;
  link?: string;
  path?: string;
  items?: Link[];
}
const rawSidebar = yaml(readFileSync("data/sidebar.yaml", "utf8")) as Group[];
export const sidebar: Group[] = rawSidebar.map((group) => ({
  ...group,
  ...(group.link ? { link: withBase(group.link) } : {}),
  ...(group.path ? { path: withBase(group.path) } : {}),
  ...(group.items
    ? { items: group.items.map((item) => ({ ...item, path: withBase(item.path) })) }
    : {}),
}));
export interface Phase {
  id: string | number;
  status: string;
  title: string;
  summary: string;
}
export const groups = yaml(readFileSync("data/roadmap.yaml", "utf8")).groups as {
  label: string;
  note: string;
  phases: Phase[];
}[];
export const releases = JSON.parse(
  readFileSync("../src/baldric/runtime/data/release-notes/releases.json", "utf8"),
) as { version: string; date: string; sections: Record<string, string[]> }[];
export function pagePath(id: string) {
  return id === "_index" ? "/" : `/${id.replace(/\/_index$/, "")}/`;
}
