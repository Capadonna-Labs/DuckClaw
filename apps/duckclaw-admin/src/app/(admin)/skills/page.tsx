import { redirect } from 'next/navigation';

export default function SkillsRedirectPage() {
  redirect('/plataforma?tab=skills&skillsTab=catalog');
}
