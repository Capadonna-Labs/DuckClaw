'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';

/** Fly commands del gateway (core + extensiones, p. ej. /macro) para el menú "/" del composer. */
export function useFlyCommandSuggestions(): { cmd: string; description: string }[] {
  const [flyCommands, setFlyCommands] = useState<{ cmd: string; description: string }[]>([]);
  useEffect(() => {
    let cancelled = false;
    adminService
      .listFlyCommands()
      .then((res) => {
        if (cancelled) return;
        setFlyCommands(
          (res.commands ?? []).map((c) => ({ cmd: c.cmd.split(/\s+/)[0], description: c.description }))
        );
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return flyCommands;
}
