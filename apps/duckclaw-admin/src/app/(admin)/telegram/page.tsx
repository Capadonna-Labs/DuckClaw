import { redirect } from 'next/navigation';

export default function TelegramRedirectPage() {
  redirect('/integraciones?tab=telegram');
}
