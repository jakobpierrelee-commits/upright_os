export type MainTabId = 'setup' | 'ide' | 'tune' | 'playground';

export type TabIntent = 'discover' | 'build' | 'operate' | 'simulate';

export type TabDefinition = {
  id: MainTabId;
  label: string;
  order: number;
  intent: TabIntent;
  icon: string;
  hotkey: string;
  statusSource: string;
  keepAlive: boolean;
};

export const TAB_DEFINITIONS: ReadonlyArray<TabDefinition> = [
  {
    id: 'setup',
    label: '1_SETUP',
    order: 1,
    intent: 'discover',
    icon: '◇',
    hotkey: 'Ctrl+1',
    statusSource: 'connect-readiness',
    keepAlive: false,
  },
  {
    id: 'ide',
    label: '2_IDE',
    order: 2,
    intent: 'build',
    icon: '▣',
    hotkey: 'Ctrl+2',
    statusSource: 'firmware-workbench',
    keepAlive: true,
  },
  {
    id: 'tune',
    label: '3_TUNE',
    order: 3,
    intent: 'operate',
    icon: '◉',
    hotkey: 'Ctrl+3',
    statusSource: 'telemetry-hud',
    keepAlive: true,
  },
  {
    id: 'playground',
    label: '4_PLAYGROUND',
    order: 4,
    intent: 'simulate',
    icon: '◎',
    hotkey: 'Ctrl+4',
    statusSource: 'iteration-bench',
    keepAlive: false,
  },
];

const TAB_ID_SET = new Set<MainTabId>(TAB_DEFINITIONS.map((t) => t.id));

export function isMainTabId(value: string | null | undefined): value is MainTabId {
  if (!value) return false;
  return TAB_ID_SET.has(value as MainTabId);
}
