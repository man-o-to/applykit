import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const page = readFileSync(
  new URL('../routes/smart-apply/+page.svelte', import.meta.url),
  'utf8',
);

describe('smart apply structured salary', () => {
  test('auto-populates min/max salary from the analyzed job and passes it to the tracker', () => {
    expect(page).toContain('minSalary = analyzed.min_salary');
    expect(page).toContain('maxSalary = analyzed.max_salary');
    expect(page).toContain('min_salary: minSalary');
    expect(page).toContain('max_salary: maxSalary');
  });

  test('replaces the free-text salary input with editable min/max fields', () => {
    expect(page).not.toContain('id="salary"');
    expect(page).toContain('id="min-salary"');
    expect(page).toContain('id="max-salary"');
  });
});
