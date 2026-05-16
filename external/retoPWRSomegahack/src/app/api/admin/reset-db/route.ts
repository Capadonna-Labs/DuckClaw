import { NextResponse } from 'next/server';
import { query, ensureSchema } from '@/lib/motherduck';

/**
 * POST /api/admin/reset-db
 * ⚠️ PELIGRO: Limpia tablas CRM en la DuckDB local para presentaciones limpias.
 */
export async function POST() {
  try {
    await ensureSchema();

    console.log('[Admin] Iniciando reset de tablas pqrsd_crm...');

    await query('DELETE FROM pqrsd_crm.tickets');
    
    try {
      await query('DELETE FROM pqrsd_crm.registros_email');
    } catch {
      // Ignorar si la tabla no existe aún
    }

    console.log('[Admin] Tablas CRM limpiadas');

    return NextResponse.json({
      success: true,
      message: 'Base de datos limpiada correctamente',
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('[Admin] Error en reset de DB:', error);
    return NextResponse.json({
      success: false,
      error: error instanceof Error ? error.message : 'Error desconocido'
    }, { status: 500 });
  }
}
