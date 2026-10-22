import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import Lenis from "lenis";
import { MOTION_OK, smooth } from "./scroll";

gsap.registerPlugin(ScrollTrigger, SplitText);

export { gsap, ScrollTrigger, SplitText };

export { MOTION_OK };
export const EXPO = "expo.out";

/**
 * Inertial scrolling for the standalone site only. An embedding host owns its own scroll, so
 * the app never attaches Lenis there. Reduced motion stops it; turning it back on restarts it.
 */
export function startSmoothScroll(): () => void {
  const mq = window.matchMedia(MOTION_OK);
  const on = () => {
    if (smooth.lenis || !mq.matches) return;
    smooth.lenis = new Lenis({ lerp: 0.11, smoothWheel: true, autoRaf: true });
    smooth.lenis.on("scroll", ScrollTrigger.update);
  };
  const off = () => {
    smooth.lenis?.destroy();
    smooth.lenis = null;
  };
  const change = () => (mq.matches ? on() : off());
  on();
  mq.addEventListener("change", change);
  return () => {
    mq.removeEventListener("change", change);
    off();
  };
}

/**
 * Pointer-only flourishes, delegated from the app root so they reach elements rendered later:
 * `.qf-magnetic` buttons lean toward the cursor, `.qf-plate` figure plates light their border
 * where the cursor is. Neither gates content; touch and keyboard users see the resting state.
 */
export function attachPointerEffects(root: HTMLElement): () => void {
  const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
  const motion = window.matchMedia(MOTION_OK);
  let current: HTMLElement | null = null;
  const release = (el: HTMLElement | null) => {
    if (el) gsap.to(el, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.45)" });
  };
  const move = (e: PointerEvent) => {
    if (!fine.matches || e.pointerType !== "mouse") return;
    const target = e.target as HTMLElement;
    const plate = target.closest<HTMLElement>(".qf-plate");
    if (plate) {
      const r = plate.getBoundingClientRect();
      plate.style.setProperty("--qf-mx", `${e.clientX - r.left}px`);
      plate.style.setProperty("--qf-my", `${e.clientY - r.top}px`);
    }
    const mag = motion.matches ? target.closest<HTMLElement>(".qf-magnetic") : null;
    if (mag !== current) {
      release(current);
      current = mag;
    }
    if (mag) {
      const r = mag.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      gsap.to(mag, { x: dx * 0.22, y: dy * 0.32, duration: 0.45, ease: "power3.out" });
    }
  };
  const leave = () => {
    release(current);
    current = null;
  };
  root.addEventListener("pointermove", move);
  root.addEventListener("pointerleave", leave);
  return () => {
    root.removeEventListener("pointermove", move);
    root.removeEventListener("pointerleave", leave);
  };
}

/** Masked line reveal for a heading, played once when it scrolls in. Text stays visible until then. */
export function revealLines(el: Element, opts: { delay?: number; scroll?: boolean } = {}) {
  const split = SplitText.create(el, { type: "lines", mask: "lines", linesClass: "qf-line" });
  gsap.from(split.lines, {
    yPercent: 110,
    duration: 1,
    ease: EXPO,
    stagger: 0.08,
    delay: opts.delay ?? 0,
    immediateRender: !opts.scroll,
    scrollTrigger: opts.scroll ? { trigger: el, start: "top 92%", once: true } : undefined,
  });
  return split;
}
