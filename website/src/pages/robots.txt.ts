import type { APIContext } from "astro";
import { withBase } from "../data";

export function GET({ site }: APIContext) {
  return new Response(
    `User-agent: *\nAllow: /\nSitemap: ${new URL(withBase("/sitemap-index.xml"), site)}\n`,
  );
}
