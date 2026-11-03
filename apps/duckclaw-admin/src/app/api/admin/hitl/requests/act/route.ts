import { NextRequest } from 'next/server';
import { proxyGatewayAdmin } from '@/lib/adminGatewayProxy';

export const POST = (req: NextRequest) => proxyGatewayAdmin(req, '/hitl/requests/act', ['admin'], 'HITL');
