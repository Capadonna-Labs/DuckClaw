import { redirect } from 'next/navigation';

/** Índice de integraciones: redirige al primer hijo del menú. */
export default function IntegrationsIndexPage() {
  redirect('/telegram');
}
