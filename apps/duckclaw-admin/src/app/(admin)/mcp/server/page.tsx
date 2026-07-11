import { redirect } from 'next/navigation';

export default function McpServerRedirectPage() {
  redirect('/mcp?tab=config');
}
