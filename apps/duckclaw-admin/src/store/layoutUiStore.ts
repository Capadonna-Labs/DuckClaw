import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface LayoutUiState {
  /** Menú lateral izquierdo (desktop). */
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  /** Panel de chat lateral derecho. */
  chatDrawerOpen: boolean;
  setChatDrawerOpen: (open: boolean) => void;
  toggleChatDrawer: () => void;
}

export const useLayoutUiStore = create<LayoutUiState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      chatDrawerOpen: false,
      setChatDrawerOpen: (open) => set({ chatDrawerOpen: open }),
      toggleChatDrawer: () => set((s) => ({ chatDrawerOpen: !s.chatDrawerOpen })),
    }),
    {
      name: 'duckclaw-admin-layout-ui',
      partialize: (s) => ({ sidebarOpen: s.sidebarOpen, chatDrawerOpen: s.chatDrawerOpen }),
    }
  )
);
