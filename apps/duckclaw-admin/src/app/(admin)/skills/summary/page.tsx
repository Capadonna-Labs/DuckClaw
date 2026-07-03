import { redirect } from 'next/navigation';

export default function SkillsSummaryRedirectPage() {
  redirect('/plataforma?tab=skills&skillsTab=catalog');
}
