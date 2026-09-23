import { create } from 'zustand';
import type { RegionCode } from '@/types/domain';

export type PanelTab = 'engineers' | 'unassigned' | 'metrics' | 'replan';

// UI-only state (06_spec_frontend.md §4): no business data (plans, tickets,
// engineers, metrics) lives here — that is owned exclusively by the
// TanStack Query cache. `baselinePlanId` is a session pointer (which cached
// plan is "the baseline"), not a duplicate of its data.
interface UiState {
  selectedRegion: RegionCode | null;
  setSelectedRegion: (region: RegionCode | null) => void;

  activeTab: PanelTab;
  setActiveTab: (tab: PanelTab) => void;

  selectedTicketId: number | null;
  openTicket: (ticketId: number) => void;
  closeTicket: () => void;

  highlightedEngineerId: number | null;
  toggleHighlightedEngineer: (engineerId: number) => void;

  diffHighlightActive: boolean;
  diffDetailsOpen: boolean;
  setDiffHighlightActive: (active: boolean) => void;
  toggleDiffDetails: () => void;

  baselinePlanId: number | null;
  setBaselinePlanId: (planId: number | null) => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  selectedRegion: null,
  setSelectedRegion: (region) => set({ selectedRegion: region }),

  activeTab: 'engineers',
  setActiveTab: (tab) => set({ activeTab: tab }),

  selectedTicketId: null,
  openTicket: (ticketId) => set({ selectedTicketId: ticketId }),
  closeTicket: () => set({ selectedTicketId: null }),

  highlightedEngineerId: null,
  toggleHighlightedEngineer: (engineerId) =>
    set({ highlightedEngineerId: get().highlightedEngineerId === engineerId ? null : engineerId }),

  diffHighlightActive: false,
  diffDetailsOpen: false,
  setDiffHighlightActive: (active) => set({ diffHighlightActive: active, diffDetailsOpen: false }),
  toggleDiffDetails: () => set({ diffDetailsOpen: !get().diffDetailsOpen }),

  baselinePlanId: null,
  setBaselinePlanId: (planId) => set({ baselinePlanId: planId })
}));
