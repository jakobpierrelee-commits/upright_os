import { useCallback, useEffect, useState } from 'react';

export type StageRoute = 'stage-1' | 'stage-2' | 'stage-3';
export type ModulePage = 'connect' | 'control' | 'tuning' | 'commissioning' | 'logs';
export type RouteState = { stage: StageRoute; page: ModulePage };

export const STAGE_FLOW: Array<{ id: StageRoute; step: string; label: string }> = [
  { id: 'stage-1', step: '01', label: 'Connect + Preflight' },
  { id: 'stage-2', step: '02', label: 'Control + Tuning' },
  { id: 'stage-3', step: '03', label: 'Commission + Release' },
];

export function routeFromPath(pathname: string): RouteState {
  if (pathname.startsWith('/stage-2/tuning')) return { stage: 'stage-2', page: 'tuning' };
  if (pathname.startsWith('/stage-2')) return { stage: 'stage-2', page: 'control' };
  if (pathname.startsWith('/stage-3/logs')) return { stage: 'stage-3', page: 'logs' };
  if (pathname.startsWith('/stage-3')) return { stage: 'stage-3', page: 'commissioning' };
  return { stage: 'stage-1', page: 'connect' };
}

export function pathFromRoute(stage: StageRoute, page: ModulePage): string {
  if (stage === 'stage-2') return page === 'tuning' ? '/stage-2/tuning' : '/stage-2/control';
  if (stage === 'stage-3') return page === 'logs' ? '/stage-3/logs' : '/stage-3/commissioning';
  return '/stage-1';
}

export function useStageRoute() {
  const [route, setRoute] = useState<RouteState>(() => routeFromPath(window.location.pathname));

  useEffect(() => {
    const next = routeFromPath(window.location.pathname);
    const canonical = pathFromRoute(next.stage, next.page);
    if (window.location.pathname !== canonical) {
      window.history.replaceState({}, '', canonical);
    }
    setRoute(next);
    const onPopState = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigateTo = useCallback((next: RouteState) => {
    const target = pathFromRoute(next.stage, next.page);
    if (window.location.pathname !== target) {
      window.history.pushState({}, '', target);
    }
    setRoute(next);
  }, []);

  return { route, navigateTo };
}
