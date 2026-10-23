import { useState } from 'react';

/** True when the page runs inside an iframe (the dashboard's chat panel): the console's side menu would only crowd it. */
export function useEmbedded(): boolean {
  const [embedded] = useState(() => {
    try {
      return typeof window !== 'undefined' && window.self !== window.top;
    } catch {
      return true; // a cross-origin parent throws: that is a frame too
    }
  });
  return embedded;
}
