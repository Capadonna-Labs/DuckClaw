import assert from 'node:assert/strict';
import { navEntriesForRole } from './adminNav';

function labelsFor(role: 'admin' | 'user' | 'viewer'): string[] {
  return navEntriesForRole(role).flatMap((entry) =>
    entry.type === 'item' ? [entry.item.label] : entry.group.items.map((item) => item.label)
  );
}

const userLabels = labelsFor('user');
assert.deepEqual(userLabels, [
  'Inicio',
  'Chat',
  'Mis agentes',
  'Crear agente',
  'Tablero',
  'Ajustes',
]);
assert.equal(userLabels.includes('Runtime overrides'), false);
assert.equal(userLabels.includes('DuckDB'), false);

const legacyViewerLabels = labelsFor('viewer');
assert.deepEqual(legacyViewerLabels, userLabels);

const adminLabels = labelsFor('admin');
assert.equal(adminLabels.includes('Overview'), true);
assert.equal(adminLabels.includes('Runtime overrides'), true);
assert.equal(adminLabels.includes('Usuarios y roles'), true);
assert.equal(adminLabels.includes('Inicio'), false);

console.log('adminNav.test.ts: ok');
