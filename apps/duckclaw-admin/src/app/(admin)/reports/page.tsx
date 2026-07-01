import { redirect } from 'next/navigation';

export default function ReportsRedirectPage() {
  redirect('/productividad?tab=reportes');
}
