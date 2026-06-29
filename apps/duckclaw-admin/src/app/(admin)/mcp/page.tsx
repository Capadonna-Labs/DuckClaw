'use client';

import { Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import { McpUnifiedView } from '@/components/mcp/McpUnifiedView';

export default function McpPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <Loader2 className="animate-spin text-gov-blue-700" size={32} />
        </div>
      }
    >
      <McpUnifiedView />
    </Suspense>
  );
}
