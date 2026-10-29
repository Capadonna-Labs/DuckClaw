import { NextRequest } from 'next/server';
import { proxyGatewayAdmin } from '@/lib/adminGatewayProxy';

// Every user manages their own worlds: the Gateway scopes reads and writes to tenant + actor.
const proxy = (req: NextRequest) => proxyGatewayAdmin(req, '/worlds', ['admin', 'user'], 'Worlds');

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
