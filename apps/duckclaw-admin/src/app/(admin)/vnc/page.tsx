import { redirect } from 'next/navigation';

/** VNC integrado en /sandbox?tab=browser */
export default function VncRedirectPage() {
  redirect('/sandbox?tab=browser');
}
