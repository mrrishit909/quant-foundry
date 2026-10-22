import { useCallback, useEffect, useState } from "react";
import type { Routing } from "./config";

/** App routes. Hash routing keeps deep links working on GitHub Pages without server rewrites. */
export type Route =
  | { view: "overview"; runId?: string }
  | { view: "strategy"; runId?: string; strategyId: string }
  | { view: "runs" }
  | { view: "compare"; a?: string; b?: string }
  | { view: "assumptions"; runId?: string }
  | { view: "request" }
  | { view: "about" };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const [head, a, b, c] = parts;
  if (head === "runs" && a && b === "strategy" && c) return { view: "strategy", runId: a, strategyId: c };
  if (head === "runs" && a && b === "assumptions") return { view: "assumptions", runId: a };
  if (head === "runs" && a) return { view: "overview", runId: a };
  if (head === "runs") return { view: "runs" };
  if (head === "compare") return { view: "compare", a, b };
  if (head === "strategy" && a) return { view: "strategy", strategyId: a };
  if (head === "assumptions") return { view: "assumptions" };
  if (head === "request") return { view: "request" };
  if (head === "about") return { view: "about" };
  return { view: "overview" };
}

export function routeHref(route: Route): string {
  const enc = encodeURIComponent;
  switch (route.view) {
    case "overview":
      return route.runId ? `#/runs/${enc(route.runId)}` : "#/";
    case "strategy":
      return route.runId ? `#/runs/${enc(route.runId)}/strategy/${enc(route.strategyId)}` : `#/strategy/${enc(route.strategyId)}`;
    case "runs":
      return "#/runs";
    case "compare":
      return `#/compare${route.a ? `/${enc(route.a)}` : ""}${route.b ? `/${enc(route.b)}` : ""}`;
    case "assumptions":
      return route.runId ? `#/runs/${enc(route.runId)}/assumptions` : "#/assumptions";
    case "request":
      return "#/request";
    case "about":
      return "#/about";
  }
}

/** Route state. In "memory" mode the host page's URL is never read or written. */
export function useRoute(mode: Routing): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(() => (mode === "hash" ? parseRoute(window.location.hash) : { view: "overview" }));
  useEffect(() => {
    if (mode !== "hash") return;
    const onHash = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [mode]);
  const navigate = useCallback(
    (r: Route) => {
      if (mode === "hash") window.location.hash = routeHref(r).slice(1);
      else setRoute(r);
    },
    [mode],
  );
  return [route, navigate];
}
