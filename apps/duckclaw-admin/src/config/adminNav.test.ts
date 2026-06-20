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
assert.deepEqual(userLabels, ['Inicio', 'Chat', 'Mis agentes', 'Proyectos', 'Ajustes']);
assert.equal(userLabels.includes('Runtime overrides'), false);
assert.equal(userLabels.includes('DuckDB'), false);

const legacyViewerLabels = labelsFor('viewer');
assert.deepEqual(legacyViewerLabels, userLabels);

const adminLabels = labelsFor('admin');
assert.equal(adminLabels.includes('Chat'), true);
assert.equal(adminLabels.includes('Runtime overrides'), true);
assert.equal(adminLabels.includes('Usuarios y roles'), true);
assert.equal(adminLabels.includes('Inicio'), false);

const adminGroups = groupLabelsFor('admin');
assert.equal(adminGroups.includes('Conversar'), true);
assert.equal(adminGroups.includes('Conectar'), true);
assert.equal(adminGroups.includes('Playground'), false);
assert.equal(adminGroups.includes('Inicio'), false);

const buildGroup = navEntriesForRole('admin').find(
  (e) => e.type === 'group' && e.group.id === 'build'
);
assert.ok(buildGroup?.type === 'group');
const buildLabels = buildGroup.group.items.map((i) => i.label);
assert.equal(buildLabels.includes('Integraciones'), false);

console.log('adminNav.test.ts: ok');
