import { redirect } from 'next/navigation';

export default function McpRuntimeRedirectPage() {
  redirect('/mcp?tab=runtime');
}
