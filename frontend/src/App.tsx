import { type MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, ErrorState, LoadingState, Segmented, useIndicator } from "./components/Controls";
import { Icon } from "./components/Icon";
import { type AppConfig, resolveConfig, type Theme } from "./config";
import { useRun, useSiteData } from "./data/snapshot";
import { ago, timestamp } from "./lib/format";
import { scrollToElement } from "./lib/scroll";
import { useKinetic } from "./lib/useKinetic";
import { parseRoute, type Route, routeHref, useRoute } from "./routing";
import { Report } from "./views/Report";
import { CompareView, RunsView } from "./views/Runs";
import { MethodView, RequestView } from "./views/Pages";
import { StrategyView } from "./views/Strategy";
import "./styles/app.css";

const NAV: { label: string; route: Route; match: Route["view"][] }[] = [
  { label: "Report", route: { view: "overview" }, match: ["overview", "strategy", "assumptions"] },
  { label: "Runs", route: { view: "runs" }, match: ["runs", "compare"] },
  { label: "Request a run", route: { view: "request" }, match: ["request"] },
  { label: "Method", route: { view: "about" }, match: ["about"] },
];

function useResolvedTheme(theme: Theme): "light" | "dark" {
  const query = "(prefers-color-scheme: dark)";
  const [system, setSystem] = useState<"light" | "dark">(() =>
    typeof window !== "undefined" && window.matchMedia?.(query).matches ? "dark" : "light",
  );
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setSystem(mq.matches ? "dark" : "light");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return theme === "auto" ? system : theme;
}

export function QuantFoundryApp(props: Partial<AppConfig>) {
  const config = useMemo(() => resolveConfig(props), [props.basePath, props.dataUrl, props.theme, props.showShell, props.routing, props.repoUrl, props.siteUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  const [themeChoice, setThemeChoice] = useState<Theme>(config.theme);
  const theme = useResolvedTheme(themeChoice);
  const [route, navigate] = useRoute(config.routing);
  const { state, reload } = useSiteData(config.dataUrl);
  const [tick, setTick] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  const navigated = useRef(false); // set after the first in-app navigation; the first load has its own intro
  const [hidden, setHidden] = useState(false);
  const standalone = config.showShell && config.routing === "hash";

  // Inertial scroll and pointer flourishes belong to the standalone site, never to a host page.
  useKinetic((k) => (standalone ? k.startSmoothScroll() : undefined), [standalone]);
  useKinetic((k) => (rootRef.current ? k.attachPointerEffects(rootRef.current) : undefined), []);

  // The masthead steps aside while reading down the page and returns on any upward scroll.
  useEffect(() => {
    if (!config.showShell) return;
    let last = window.scrollY;
    let frame = 0;
    const on = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const y = window.scrollY;
        if (Math.abs(y - last) > 6) setHidden(y > 160 && y > last);
        last = y;
      });
    };
    window.addEventListener("scroll", on, { passive: true });
    return () => {
      window.removeEventListener("scroll", on);
      cancelAnimationFrame(frame);
    };
  }, [config.showShell]);

  const needsRun = route.view === "overview" || route.view === "strategy" || route.view === "assumptions";
  const latest = state.status === "ready" ? state.data.snapshot.latest_run_id : null;
  const runId = needsRun ? ("runId" in route && route.runId ? route.runId : latest) : null;
  const run = useRun(config.dataUrl, state.status === "ready" ? runId : null, tick);

  const routeKey = JSON.stringify(route);
  useEffect(() => {
    setMenuOpen(false);
    if (first.current) {
      first.current = false;
      return;
    }
    navigated.current = true;
    if (route.view !== "assumptions" && mainRef.current) {
      scrollToElement(mainRef.current, { immediate: true, offset: 0 });
      mainRef.current.focus({ preventScroll: true });
    }
  }, [routeKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Navigation transition: each view's headline rises out of a mask and the body follows it in.
  const viewKey = `${routeKey}:${state.status}:${run.status}`;
  useKinetic(({ gsap, MOTION_OK, revealLines }, late) => {
    const main = mainRef.current;
    if (!main) return;
    const mm = gsap.matchMedia();
    mm.add(MOTION_OK, () => {
      const h1 = main.querySelector("h1:not(.qf-hero-title)");
      if (h1 && !late) revealLines(h1);
      if (navigated.current && !main.querySelector(".qf-hero-title")) {
        gsap.from(main.children, { y: 24, opacity: 0, duration: 0.6, ease: "power3.out", clearProps: "transform,opacity" });
      }
    });
    return () => mm.revert();
  }, [viewKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => {
    reload();
    setTick((t) => t + 1);
  };

  // Hash links inside the app are routed here, so "memory" routing never touches the host URL.
  const onClick = (e: MouseEvent<HTMLDivElement>) => {
    const a = (e.target as HTMLElement).closest("a");
    const href = a?.getAttribute("href");
    if (!a || !href?.startsWith("#/") || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    if (config.routing === "memory") {
      e.preventDefault();
      navigate(parseRoute(href));
    }
  };

  const activeNav = NAV.find((n) => n.match.includes(route.view))?.label;
  const { container: navRef, style: navStyle } = useIndicator<HTMLElement>('a[aria-current="page"]', activeNav);

  let body: React.ReactNode;
  if (state.status === "loading") body = <LoadingState what="the research snapshot" />;
  else if (state.status === "error")
    body = <ErrorState title="The research snapshot did not load" error={state.error} onRetry={refresh} />;
  else if (state.status === "empty" && needsRun) body = <EmptyState requestHref={routeHref({ view: "request" })} />;
  else if (route.view === "request") body = <RequestView config={config} />;
  else if (route.view === "about") body = <MethodView config={config} />;
  else if (state.status !== "ready") body = <EmptyState requestHref={routeHref({ view: "request" })} />;
  else if (route.view === "runs") body = <RunsView site={state.data} config={config} />;
  else if (route.view === "compare")
    body = <CompareView site={state.data} config={config} a={route.a} b={route.b} navigate={navigate} />;
  else if (run.status === "loading") body = <LoadingState what={`run ${runId}`} />;
  else if (run.status === "error")
    body = (
      <ErrorState
        title={runId && !state.data.snapshot.runs_included.includes(runId) ? `Run ${runId} is not in this snapshot` : "This run did not load"}
        error={run.error}
        onRetry={refresh}
      />
    );
  else if (run.status === "ready" && route.view === "strategy")
    body = <StrategyView run={run.data} strategyId={route.strategyId} />;
  else if (run.status === "ready")
    body = <Report run={run.data} snapshot={state.data.snapshot} config={config} focus={route.view === "assumptions" ? "assumptions" : undefined} />;
  else body = <EmptyState requestHref={routeHref({ view: "request" })} />;

  const snap = state.status === "ready" ? state.data.snapshot : null;
  const release = state.status === "ready" ? state.data.release : null;

  return (
    <div className="qf-root" data-theme={theme} onClick={onClick} data-app-root="quant-foundry" ref={rootRef}>
      <a className="qf-skip" href="#qf-main" onClick={(e) => { e.preventDefault(); mainRef.current?.focus(); }}>
        Skip to content
      </a>
      {config.showShell && (
        <header className="qf-masthead" data-hidden={hidden && !menuOpen}>
          <a className="qf-wordmark" href={routeHref({ view: "overview" })}>
            Quant Foundry<span>Research lab</span>
          </a>
          <nav className="qf-nav" aria-label="Primary" data-open={menuOpen} ref={navRef} id="qf-primary-nav">
            {navStyle && <span className="qf-nav-indicator" style={navStyle} aria-hidden />}
            {NAV.map((n) => (
              <a key={n.label} href={routeHref(n.route)} aria-current={n.label === activeNav ? "page" : undefined}>
                {n.label}
              </a>
            ))}
            {snap && <span className="qf-small qf-nav-snapshot">Snapshot generated {ago(snap.generated_at)}</span>}
          </nav>
          <div className="qf-mast-tools">
            {snap && (
              <span className="qf-small qf-hide-sm" title={timestamp(snap.generated_at)}>
                Snapshot {ago(snap.generated_at)}
              </span>
            )}
            <button type="button" className="qf-btn qf-btn-quiet qf-magnetic" onClick={refresh} aria-label="Refresh data from the published snapshot">
              <Icon name="refresh" /> <span className="qf-hide-sm">Refresh</span>
            </button>
            <button
              type="button"
              className="qf-btn qf-menu-button"
              aria-expanded={menuOpen}
              aria-controls="qf-primary-nav"
              onClick={() => setMenuOpen((o) => !o)}
            >
              <Icon name="menu" /> Menu
            </button>
          </div>
        </header>
      )}
      {snap?.mode === "fixture" && (
        <div className="qf-banner" role="note">
          <Icon name="info" /> Fixture data: a real engine run built for automated browser tests, not a published research run.
        </div>
      )}
      {state.status === "ready" && state.stale && snap && (
        <div className="qf-banner" role="status">
          <span className="qf-tone-warning"><Icon name="warn" /></span>
          <span>
            This snapshot is {ago(snap.generated_at)} old, older than its 14-day freshness window. Scheduled refreshes can
            run late or pause; the results shown are still the last ones published.
          </span>
          <button type="button" className="qf-btn" onClick={refresh}><Icon name="refresh" /> Refresh</button>
        </div>
      )}
      {release?.status === "blocked" && (
        <div className="qf-banner" role="status">
          <span className="qf-tone-danger"><Icon name="cross" /></span>
          <span>The latest release check is blocked: {release.findings.filter((f) => f.status === "fail").map((f) => f.title).join("; ")}.</span>
        </div>
      )}
      <main className="qf-page" id="qf-main" ref={mainRef} tabIndex={-1} style={{ outline: "none" }}>
        {body}
      </main>
      {config.showShell && (
        <footer className="qf-footer">
          <p className="qf-outro" aria-hidden>Quant <em>Foundry</em></p>
          <div style={{ display: "grid", gap: 10 }}>
            <p>
              Historical simulation on synthetic data. No orders are placed and nothing here is investment advice.
              {snap ? ` Snapshot generated ${timestamp(snap.generated_at)}.` : ""}
              {release ? ` Latest release check: ${release.status} (${timestamp(release.created_at)}).` : ""}
            </p>
            <Segmented
              label="Colour theme"
              value={themeChoice}
              options={[{ value: "auto", label: "System" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]}
              onChange={setThemeChoice}
            />
          </div>
          <nav aria-label="Project links">
            <a href={config.repoUrl}><Icon name="github" /> Source</a>
            <a href={`${config.repoUrl}/tree/state`}>State branch</a>
            <a href={`${config.repoUrl}/blob/main/docs/ARCHITECTURE.md`}>Architecture</a>
          </nav>
        </footer>
      )}
    </div>
  );
}
