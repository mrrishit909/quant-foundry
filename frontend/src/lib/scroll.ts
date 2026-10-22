import type Lenis from "lenis";

/** Every GSAP tween is registered under this query, so turning on reduced motion reverts it live. */
export const MOTION_OK = "(prefers-reduced-motion: no-preference)";

/** The running Lenis instance, set by the motion chunk once it loads (standalone site only). */
export const smooth: { lenis: Lenis | null } = { lenis: null };

/** Scroll an element under the sticky masthead, through Lenis when it is running. */
export function scrollToElement(el: HTMLElement, opts: { immediate?: boolean; offset?: number } = {}) {
  const offset = opts.offset ?? -88;
  if (smooth.lenis) {
    smooth.lenis.scrollTo(el, { offset, immediate: opts.immediate, duration: 1.1 });
    return;
  }
  const top = el.getBoundingClientRect().top + window.scrollY + offset;
  const reduced = !window.matchMedia(MOTION_OK).matches;
  window.scrollTo({ top, behavior: opts.immediate || reduced ? "auto" : "smooth" });
}
