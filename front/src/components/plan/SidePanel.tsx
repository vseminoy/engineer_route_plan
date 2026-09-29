import { EngineerListTab } from './EngineerListTab';
import { UnassignedListTab } from './UnassignedListTab';
import { MetricsTab } from './MetricsTab';
import { ReplanTab } from './ReplanTab';
import { useUiStore, type PanelTab } from '@/store/useUiStore';
import type { DonePlan, EngineerRoster, TicketSummary } from '@/types/domain';

interface Props {
  plan: DonePlan;
  roster: EngineerRoster[];
  ticketById: Map<number, TicketSummary>;
  onReplanned: (newPlanId: number) => void;
}

const TABS: Array<{ id: PanelTab; label: string }> = [
  { id: 'engineers', label: 'Бригады' },
  { id: 'unassigned', label: 'Не назначено' },
  { id: 'metrics', label: 'Метрики' },
  { id: 'replan', label: 'События' }
];

export function SidePanel({ plan, roster, ticketById, onReplanned }: Props) {
  const activeTab = useUiStore((s) => s.activeTab);
  const setActiveTab = useUiStore((s) => s.setActiveTab);

  return (
    <div className="side-panel">
      <div className="side-panel__tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`side-panel__tab${activeTab === tab.id ? ' side-panel__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.id === 'unassigned' && plan.unassigned.length > 0 && (
              <span
                style={{
                  marginLeft: 4,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  minWidth: 16,
                  height: 16,
                  padding: '0 4px',
                  borderRadius: 8,
                  background: 'var(--color-danger)',
                  color: '#fff',
                  fontSize: 10,
                  fontWeight: 600
                }}
              >
                {plan.unassigned.length}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="side-panel__body">
        {activeTab === 'engineers' && <EngineerListTab plan={plan} roster={roster} ticketById={ticketById} />}
        {activeTab === 'unassigned' && <UnassignedListTab plan={plan} ticketById={ticketById} />}
        {activeTab === 'metrics' && <MetricsTab plan={plan} />}
        {activeTab === 'replan' && <ReplanTab plan={plan} roster={roster} ticketById={ticketById} onReplanned={onReplanned} />}
      </div>
    </div>
  );
}
