'use client';

import { useCallback, useEffect, useState } from 'react';
import { DEVELOPER_MODE_EVENT, readDeveloperMode, writeDeveloperMode } from '@/lib/developerMode';

export function useDeveloperMode() {
  const [developerMode, setDeveloperModeState] = useState(false);

  useEffect(() => {
    setDeveloperModeState(readDeveloperMode());
    const sync = () => setDeveloperModeState(readDeveloperMode());
    window.addEventListener(DEVELOPER_MODE_EVENT, sync);
    return () => window.removeEventListener(DEVELOPER_MODE_EVENT, sync);
  }, []);

  const setDeveloperMode = useCallback((enabled: boolean) => {
    writeDeveloperMode(enabled);
    setDeveloperModeState(enabled);
  }, []);

  return { developerMode, setDeveloperMode };
}
