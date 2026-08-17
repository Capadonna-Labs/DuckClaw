import { readFile } from 'fs/promises';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';

import { requireAdminRouteAuth } from '@/lib/adminRouteAuth';
import {
  guessChatDocumentMime,
  isAllowedChatDocumentName,
} from '@/lib/chatDocumentAttachments';
import { isDesktopLiteMode } from '@/lib/desktopEnvFile';
import { isDesktopBuild } from '@/lib/tauriRuntime';

const MAX_FILES = 5;
const MAX_BYTES = 5 * 1024 * 1024;
const IMAGE_EXT = new Set(['.jpg', '.jpeg', '.png', '.webp']);

function isAllowedName(name: string): boolean {
  const base = path.basename(name);
  const ext = path.extname(base).toLowerCase();
  return IMAGE_EXT.has(ext) || isAllowedChatDocumentName(base);
}

function resolveSafeAbsolutePath(raw: string): string | null {
  const input = (raw || '').trim().replace(/^\\\\\?\\/, '');
  if (!input) return null;
  if (input.includes('\0')) return null;
  const resolved = path.resolve(input);
  // Solo rutas absolutas Windows/Unix; sin traversal residual.
  if (!path.isAbsolute(resolved)) return null;
  if (resolved.includes('..')) return null;
  return resolved;
}

/** Drop nativo Tauri → lee bytes locales para el compositor del chat. */
export async function POST(req: NextRequest) {
  const auth = await requireAdminRouteAuth(req, { roles: ['admin', 'user'] });
  if (!auth.ok) return auth.response;

  if (!isDesktopBuild() && !isDesktopLiteMode()) {
    return NextResponse.json(
      { detail: 'Solo disponible en DuckClaw desktop' },
      { status: 403 }
    );
  }

  let body: { paths?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: 'JSON inválido' }, { status: 400 });
  }

  const rawPaths = Array.isArray(body.paths) ? body.paths : [];
  const paths = rawPaths
    .map((p) => (typeof p === 'string' ? p : ''))
    .map(resolveSafeAbsolutePath)
    .filter((p): p is string => Boolean(p));

  if (paths.length === 0) {
    return NextResponse.json({ detail: 'paths requeridos' }, { status: 400 });
  }
  if (paths.length > MAX_FILES) {
    return NextResponse.json(
      { detail: `Máximo ${MAX_FILES} archivos por soltar` },
      { status: 400 }
    );
  }

  const files: {
    name: string;
    mime_type: string;
    data_base64: string;
    size: number;
  }[] = [];

  for (const filePath of paths) {
    const name = path.basename(filePath);
    if (!isAllowedName(name)) {
      return NextResponse.json(
        {
          detail: `Formato no admitido: ${name}. Usa PDF, Word, Excel, CSV, TXT, MD, PowerPoint, HTML o imágenes.`,
        },
        { status: 400 }
      );
    }
    let data: Buffer;
    try {
      // Solo lectura: nunca abrimos el original en modo escritura ni lo modificamos.
      data = await readFile(filePath);
    } catch {
      return NextResponse.json(
        { detail: `No se pudo leer: ${name}` },
        { status: 400 }
      );
    }
    if (data.byteLength > MAX_BYTES) {
      return NextResponse.json(
        { detail: `${name} supera ${MAX_BYTES / (1024 * 1024)} MB` },
        { status: 400 }
      );
    }
    const ext = path.extname(name).toLowerCase();
    const mime =
      ext === '.jpg' || ext === '.jpeg'
        ? 'image/jpeg'
        : ext === '.png'
          ? 'image/png'
          : ext === '.webp'
            ? 'image/webp'
            : guessChatDocumentMime({ name });
    files.push({
      name,
      mime_type: mime,
      data_base64: data.toString('base64'),
      size: data.byteLength,
    });
  }

  return NextResponse.json({ ok: true, files });
}
