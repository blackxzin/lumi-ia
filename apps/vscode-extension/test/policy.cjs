const test = require('node:test');
const assert = require('node:assert/strict');
const { safeRelative } = require('../dist/policy');
test('authorized source paths', () => assert.equal(safeRelative('/project', '/project/src/main.py'), 'src/main.py'));
test('private paths and traversal', () => {
  for (const file of ['/etc/passwd', '/project/.env', '/project/.git/config', '/project/credentials.json', '/project/private.key', '/project/node_modules/a.js']) {
    assert.equal(safeRelative('/project', file), undefined, file);
  }
});
