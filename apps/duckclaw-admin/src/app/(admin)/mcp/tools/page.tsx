import { redirect } from 'next/navigation';

export default function McpToolsRedirectPage() {
  redirect('/mcp?tab=tools');
}
