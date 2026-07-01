import { redirect } from 'next/navigation';

export default function IntegrationsIndexRedirectPage() {
  redirect('/integraciones?tab=telegram');
}
