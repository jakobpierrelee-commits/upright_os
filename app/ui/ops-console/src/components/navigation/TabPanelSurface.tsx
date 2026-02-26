import { useEffect, useState, type ReactNode } from 'react';
import type { MainTabId } from './tabs';

type Props = {
  id: MainTabId;
  activeTab: MainTabId;
  keepAlive: boolean;
  className?: string;
  children: ReactNode;
};

export function TabPanelSurface({ id, activeTab, keepAlive, className, children }: Props) {
  const active = activeTab === id;
  const [mounted, setMounted] = useState(active);

  useEffect(() => {
    if (active) setMounted(true);
  }, [active]);

  if (!active && !keepAlive) {
    return null;
  }

  if (!mounted) {
    return null;
  }

  return (
    <section
      id={`panel-${id}`}
      role="tabpanel"
      aria-labelledby={`tab-${id}`}
      aria-hidden={!active}
      hidden={!active}
      className={className ? `tab-panel ${className}` : 'tab-panel'}
    >
      {children}
    </section>
  );
}
