import { redirect } from 'next/navigation';

export default function GenImageRedirectPage() {
  redirect('/plataforma?tab=imagenes');
}
