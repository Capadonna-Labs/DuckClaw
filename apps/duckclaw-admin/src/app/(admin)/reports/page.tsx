import { redirect } from 'next/navigation';

/** Compat: /reports → Productividad → Artefactos → Informes */
export default function ReportsRedirectPage() {
  redirect('/productividad?tab=artefactos&view=informes');
}
