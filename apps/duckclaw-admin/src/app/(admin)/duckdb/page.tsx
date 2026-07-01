import { redirect } from 'next/navigation';

export default function DuckDbRedirectPage() {
  redirect('/plataforma?tab=duckdb');
}
