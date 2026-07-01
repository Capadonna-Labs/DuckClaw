import { redirect } from 'next/navigation';

export default function AuditRedirectPage() {
  redirect('/administracion?tab=auditoria');
}
