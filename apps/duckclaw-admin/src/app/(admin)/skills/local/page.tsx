import { redirect } from 'next/navigation';

export default function SkillsLocalRedirectPage() {
  redirect('/plataforma?tab=skills&skillsTab=catalog');
}
