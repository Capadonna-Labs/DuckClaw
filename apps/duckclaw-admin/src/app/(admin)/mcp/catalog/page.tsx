import { redirect } from 'next/navigation';

export default function McpCatalogRedirectPage() {
  redirect('/mcp?tab=catalog');
}
