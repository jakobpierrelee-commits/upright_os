import type { TabDefinition, MainTabId } from './tabs';

type Props = {
  tabs: ReadonlyArray<TabDefinition>;
  activeTab: MainTabId;
  onSelect: (tab: MainTabId) => void;
};

export function TabBar({ tabs, activeTab, onSelect }: Props) {
  return (
    <div className="ops-tabs tab-bar" role="tablist" aria-label="Primary app tabs">
      {tabs.map((tab) => {
        const active = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            id={`tab-${tab.id}`}
            role="tab"
            aria-selected={active}
            aria-controls={`panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            className={`btn-sm tab-btn tab-intent-${tab.intent} ${active ? 'active' : ''}`}
            title={`${tab.hotkey} • ${tab.statusSource}`}
            onClick={() => onSelect(tab.id)}
          >
            <span className="tab-icon" aria-hidden="true">{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
