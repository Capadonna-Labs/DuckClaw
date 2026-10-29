import { NextRequest } from 'next/server';
import { proxyGatewayAdmin } from '@/lib/adminGatewayProxy';

const proxy = (req: NextRequest) => proxyGatewayAdmin(req, '/worlds/bots', ['admin', 'user'], 'Worlds');

export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
