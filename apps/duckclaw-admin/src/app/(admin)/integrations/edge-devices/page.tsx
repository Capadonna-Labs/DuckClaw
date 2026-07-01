import { redirect } from 'next/navigation';

export default function EdgeDevicesRedirectPage() {
  redirect('/integraciones?tab=edge');
}
