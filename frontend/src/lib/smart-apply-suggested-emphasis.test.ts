import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const page = readFileSync(
  new URL('../routes/smart-apply/+page.svelte', import.meta.url),
  'utf8',
);

describe('smart apply suggested emphasis wiring', () => {
  test('feeds suggested_emphasis into both CV and cover letter generation', () => {
    const occurrences = page.match(/fit_context: fitResult\?\.suggested_emphasis \|\| null/g);
    expect(occurrences?.length).toBe(2);
  });
});
