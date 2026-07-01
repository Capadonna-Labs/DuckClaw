import { redirect } from 'next/navigation';

export default function KanbanRedirectPage() {
  redirect('/productividad?tab=tablero');
}
