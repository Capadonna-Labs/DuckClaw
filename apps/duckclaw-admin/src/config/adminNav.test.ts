import assert from 'node:assert/strict';
import { navEntriesForRole } from './adminNav';

function labelsFor(role: 'admin' | 'user' | 'viewer'): string[] {
  return navEntriesForRole(role).flatMap((entry) =>
    entry.type === 'item' ? [entry.item.label] : entry.group.items.map((item) => item.label)
  );
}

function groupLabelsFor(role: 'admin' | 'user' | 'viewer'): string[] {
  return navEntriesForRole(role)
    .filter((entry) => entry.type === 'group')
    .map((entry) => (entry.type === 'group' ? entry.group.label : ''));
}

const userLabels = labelsFor('user');
assert.deepEqual(userLabels, ['Inicio', 'Chat', 'Sandbox', 'Mis agentes', 'Proyectos', 'Ajustes']);
assert.equal(userLabels.includes('Runtime'), false);
assert.equal(userLabels.includes('DuckDB'), false);

const legacyViewerLabels = labelsFor('viewer');
assert.deepEqual(legacyViewerLabels, userLabels);

const adminLabels = labelsFor('admin');
assert.equal(adminLabels.includes('Chat'), true);
assert.equal(adminLabels.includes('Sandbox'), true);
assert.equal(adminLabels.includes('Runtime'), true);
assert.equal(adminLabels.includes('Acceso'), true);
assert.equal(adminLabels.includes('Inicio'), true);

const adminGroups = groupLabelsFor('admin');
assert.deepEqual(adminGroups, ['Trabajo', 'Estudio', 'Plataforma']);
assert.equal(adminGroups.includes('Conversar'), false);
assert.equal(adminGroups.includes('Agentes'), false);

const studioGroup = navEntriesForRole('admin').find(
  (e) => e.type === 'group' && e.group.id === 'studio'
);
assert.ok(studioGroup?.type === 'group');
const studioLabels = studioGroup.group.items.map((i) => i.label);
assert.equal(studioLabels.includes('Conocimiento'), true);
assert.equal(studioLabels.includes('VNC'), false);

console.log('adminNav.test.ts: ok');
