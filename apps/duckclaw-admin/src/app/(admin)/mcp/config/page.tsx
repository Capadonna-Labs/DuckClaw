import { redirect } from 'next/navigation';

export default function McpConfigRedirectPage() {
  redirect('/mcp?tab=config');
}
