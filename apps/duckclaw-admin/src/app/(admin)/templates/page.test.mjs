import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./page.tsx', import.meta.url), 'utf8');

assert.equal(
  source.includes('CatalogImportPanel'),
  false,
  'TemplatesPage should not render the legacy catalog import panel'
);

assert.equal(
  source.includes('Importar templates'),
  false,
  'TemplatesPage should not expose the legacy template import copy'
);

console.log('templates/page.test.mjs: ok');
