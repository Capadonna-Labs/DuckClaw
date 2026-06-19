'use client';

import type { KnowledgeSource } from '@/services/adminService';
import {
  knowledgeStatusClass,
  knowledgeStatusLabel,
  knowledgeStatusTone,
} from '@/components/knowledge/knowledgeStatusUi';

export function KnowledgeStatusBadge({ source }: { source: KnowledgeSource }) {
  const tone = knowledgeStatusTone(source);
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wide ${knowledgeStatusClass(tone)}`}
    >
      {knowledgeStatusLabel(tone)}
    </span>
  );
}
