import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

describe('canonical route compatibility', () => {
  test.each([
    ['src/routes/resume/+page.svelte', "../generate/+page.svelte"],
    ['src/routes/documents/+page.svelte', "../history/+page.svelte"],
    ['src/routes/applications/+page.svelte', "../tracker/+page.svelte"],
  ])('%s reuses the legacy workspace', (path, legacyImport) => {
    const source = readFileSync(path, 'utf8');
    expect(source).toContain(legacyImport);
  });
});
