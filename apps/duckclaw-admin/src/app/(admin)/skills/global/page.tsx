import { redirect } from 'next/navigation';

export default function SkillsGlobalRedirectPage() {
  redirect('/plataforma?tab=skills&skillsTab=catalog');
}
