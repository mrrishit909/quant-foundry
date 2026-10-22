import { type DependencyList, useEffect } from "react";

type Kinetic = typeof import("./kinetic");
let pending: Promise<Kinetic> | null = null;

/** The motion libraries (GSAP, Lenis) load as their own chunk so the first paint never waits on them. */
export const loadKinetic = () => (pending ??= import("./kinetic"));

/**
 * Runs `fn` once the motion chunk is available; its cleanup runs on unmount or when deps change.
 * `late` is true when the chunk arrived well after mount, so intros can skip rather than
 * hide content the visitor has already seen.
 */
export function useKinetic(fn: (k: Kinetic, late: boolean) => void | (() => void), deps: DependencyList) {
  useEffect(() => {
    let dead = false;
    let cleanup: void | (() => void);
    const start = performance.now();
    loadKinetic().then((k) => {
      if (!dead) cleanup = fn(k, performance.now() - start > 250);
    });
    return () => {
      dead = true;
      cleanup?.();
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}
