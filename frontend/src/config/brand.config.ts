/**
 * Brand mark — the ONE place to swap the product logo/icon.
 *
 * Generating several candidates? Drop them in `public/brand/` and change
 * `icon` (and optionally `wordmark`) below. Every surface that shows the
 * mark — marketing header, app sidebar, auth panel, loading states, the
 * footer — reads from here, so a single edit reskins the whole product.
 *
 * Coverage:
 *   - Every React surface (header, sidebar, auth, loading, footer) → swaps
 *     automatically from `icon` / `wordmark` below.
 *   - The social card (`src/app/opengraph-image.tsx`) draws the built-in
 *     geometry from here, so it tracks tweaks to the drawn mark.
 *   - The favicon (`src/app/icon.svg`) is a static file and is the one place
 *     that does NOT auto-follow: when you settle on a custom icon, replace
 *     `icon.svg` too (and the OG card if it should show the custom art).
 */

export type BrandIcon = "builtin" | (string & {});

export const brandConfig = {
  /**
   * "builtin"        → the hand-drawn ring mark (BUILTIN_MARK_RINGS below)
   * "/brand/foo.svg" → your generated icon under public/ (svg or png)
   */
  icon: "builtin" as BrandIcon,

  /**
   * Optional single-asset wordmark (icon + name baked together). When null,
   * the Wordmark renders the icon next to the site name in the display face.
   */
  wordmark: null as string | null,

  /** Alt text used when a custom raster icon is rendered. */
  alt: "Clannon",
};

/**
 * The built-in mark: tree rings in cross-section — memory laid down season by
 * season, gaps at different angles so the rings read as grown, not drawn.
 * Defined once; consumed by the React mark, the favicon, and the OG card.
 */
export const BUILTIN_MARK_RINGS: ReadonlyArray<{
  r: number;
  width: number;
  dash: string;
  rotate: number;
}> = [
  { r: 5.5, width: 1.7, dash: "26.5 8", rotate: -40 },
  { r: 9.75, width: 1.7, dash: "49 12.5", rotate: 75 },
  { r: 14, width: 1.7, dash: "71 17", rotate: 195 },
];

export const BUILTIN_MARK_CORE_R = 1.8;
