import asyncio
import httpx

REDIRECT = "https://ubuntu-2gb-ash-1.tailc95db0.ts.net/api/v1/oauth/callback"
STATIC_ID = "39cd872b-594c-8112-b52e-0037b5bc0aac"


async def main() -> None:
    async with httpx.AsyncClient(timeout=20) as c:
        reg = await c.post(
            "https://mcp.notion.com/register",
            json={
                "client_name": "DuckClaw Admin",
                "redirect_uris": [REDIRECT],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
        print("register_status", reg.status_code)
        print("register_body", reg.text[:500])
        auth = await c.get(
            "https://mcp.notion.com/authorize",
            params={
                "response_type": "code",
                "client_id": STATIC_ID,
                "redirect_uri": REDIRECT,
                "code_challenge": "test",
                "code_challenge_method": "S256",
                "resource": "https://mcp.notion.com/mcp",
            },
            follow_redirects=False,
        )
        print("static_auth_status", auth.status_code)
        print("static_auth_body", auth.text[:200])


if __name__ == "__main__":
    asyncio.run(main())
