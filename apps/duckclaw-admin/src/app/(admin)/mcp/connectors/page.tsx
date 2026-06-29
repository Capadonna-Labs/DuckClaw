import { redirect } from 'next/navigation';

export default function McpConnectorsRedirectPage() {
  redirect('/mcp?tab=connectors');
}
