import { redirect } from 'next/navigation';

export default function SkillsNewRedirectPage() {
  redirect('/plataforma?tab=skills&skillsTab=create');
}
