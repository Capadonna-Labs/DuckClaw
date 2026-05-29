import assert from 'node:assert/strict';
import { paginateItems } from './pagination';

const items = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];

assert.deepEqual(paginateItems(items, 1, 5), {
  items: ['a', 'b', 'c', 'd', 'e'],
  currentPage: 1,
  totalPages: 2,
  totalItems: 7,
});

assert.deepEqual(paginateItems(items, 2, 5), {
  items: ['f', 'g'],
  currentPage: 2,
  totalPages: 2,
  totalItems: 7,
});

assert.deepEqual(paginateItems(items, 99, 5), {
  items: ['f', 'g'],
  currentPage: 2,
  totalPages: 2,
  totalItems: 7,
});

assert.deepEqual(paginateItems([], 1, 5), {
  items: [],
  currentPage: 1,
  totalPages: 1,
  totalItems: 0,
});

console.log('pagination.test.ts: ok');
