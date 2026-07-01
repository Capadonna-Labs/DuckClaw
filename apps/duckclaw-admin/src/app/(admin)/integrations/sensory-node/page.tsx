import { redirect } from 'next/navigation';

export default function SensoryNodeRedirectPage() {
  redirect('/integraciones?tab=sensory');
}
