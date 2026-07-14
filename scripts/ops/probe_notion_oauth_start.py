import asyncio
import os

import duckdb

from duckclaw.mcp_notion_oauth import start_notion_oauth


async def main() -> None:
    db = os.environ.get("DUCKCLAW_GATEWAY_DB_PATH", "/root/Capadonna-Driller/db/duckclaw.duckdb")
    con = duckdb.connect(db)
    redirect = "https://ubuntu-2gb-ash-1.tailc95db0.ts.net/api/admin/mcp/connectors/oauth/callback"
    result = await start_notion_oauth(
        con,
        connector_id="mcp_notion",
        tenant_id="user-juanjoarevalo57-79c5ca60b91d4f3e",
        actor_email="admin@test.local",
        redirect_uri=redirect,
    )
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(result["authorization_url"]).query)
    print("redirect", result["redirect_uri"])
    print("client_id", q.get("client_id", [""])[0])
    print("auth_url_ok", result["authorization_url"].startswith("https://mcp.notion.com/authorize"))
    con.close()


if __name__ == "__main__":
    asyncio.run(main())
