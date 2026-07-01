import assert from 'node:assert/strict';
import { navEntriesForRole } from './adminNav';

function labelsFor(role: 'admin' | 'user' | 'viewer'): string[] {
  return navEntriesForRole(role).flatMap((entry) =>
    entry.type === 'item' ? [entry.item.label] : entry.group.items.map((item) => item.label)
  );
}

function primaryLabelsFor(role: 'admin' | 'user' | 'viewer'): string[] {
  const primary = navEntriesForRole(role).find(
    (entry) => entry.type === 'group' && entry.group.id === 'primary'
  );
  assert.ok(primary?.type === 'group');
  return primary.group.items.map((item) => item.label);
}

function moreLabelsFor(role: 'admin' | 'user' | 'viewer'): string[] {
  const more = navEntriesForRole(role).find(
    (entry) => entry.type === 'group' && entry.group.id === 'more'
  );
  assert.ok(more?.type === 'group');
  return more.group.items.map((item) => item.label);
}

const userLabels = labelsFor('user');
assert.deepEqual(primaryLabelsFor('user'), ['Inicio', 'Chat', 'Mis agentes', 'Conocimiento']);
assert.deepEqual(moreLabelsFor('user'), ['Proyectos', 'Sandbox']);
assert.equal(userLabels.includes('Conocimiento'), true);
assert.equal(userLabels.includes('Plataforma'), false);
assert.equal(userLabels.includes('Proyectos'), true);
assert.equal(userLabels.includes('Sandbox'), true);

const adminLabels = labelsFor('admin');
assert.deepEqual(primaryLabelsFor('admin'), ['Inicio', 'Chat', 'Agentes', 'Conocimiento']);
assert.deepEqual(moreLabelsFor('admin'), [
  'Proyectos',
  'Sandbox',
  'Productividad',
  'Plataforma',
  'Integraciones',
  'Administración',
]);
assert.equal(adminLabels.includes('DuckDB'), false);
assert.equal(adminLabels.includes('Plataforma'), true);
assert.equal(adminLabels.includes('Reglas base'), false);

const adminStructure = navEntriesForRole('admin');
assert.equal(adminStructure.length, 2);
assert.equal(adminStructure[0].type === 'group' && adminStructure[0].group.id, 'primary');
assert.equal(adminStructure[1].type === 'group' && adminStructure[1].group.id, 'more');
assert.equal(adminStructure[0].type === 'group' && adminStructure[0].group.collapsible, false);
assert.equal(adminStructure[1].type === 'group' && adminStructure[1].group.items.length, 6);

console.log('adminNav.test.ts: ok');
