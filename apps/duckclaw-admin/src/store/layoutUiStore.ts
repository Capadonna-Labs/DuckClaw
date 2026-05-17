import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface LayoutUiState {
  /** Menú lateral izquierdo (desktop). */
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
}

export const useLayoutUiStore = create<LayoutUiState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
    }),
    { name: 'duckclaw-admin-layout-ui', partialize: (s) => ({ sidebarOpen: s.sidebarOpen }) }
  )
);
