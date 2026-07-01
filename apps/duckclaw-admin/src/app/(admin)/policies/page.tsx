import { redirect } from 'next/navigation';

export default function PoliciesRedirectPage() {
  redirect('/plataforma?tab=reglas');
}
