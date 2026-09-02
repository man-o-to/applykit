import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const editor = readFileSync(
  new URL('./components/history/CoverLetterVersionEditor.svelte', import.meta.url),
  'utf8',
);
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');

describe('cover letter selection-rewrite', () => {
  test('tracks the native textarea selection without a new library', () => {
    expect(editor).toContain('selectionStart = textareaRef.selectionStart');
    expect(editor).toContain('selectionEnd = textareaRef.selectionEnd');
  });

  test('streams a preview before applying anything', () => {
    expect(editor).toContain('streamCoverLetterSelectionEdit');
    expect(editor).toContain('rewritePreview');
    expect(editor).toContain('Apply & Save Version');
  });

  test('apply sends position-based selection bounds, not just the excerpt text, to guard against drift', () => {
    expect(editor).toContain('selection_start: selectionStart');
    expect(editor).toContain('selection_end: selectionEnd');
  });

  test('is gated on unsaved local changes so it can never silently discard them', () => {
    expect(editor).toContain('{#if dirty}');
    expect(editor).toContain('Save or cancel your other unsaved changes');
  });

  test('an applied rewrite closes the editor the same way the main save does', () => {
    expect(editor).toContain('onSaved(updated);');
  });

  test('api client exposes the cover letter selection-edit endpoints', () => {
    expect(api).toContain('streamCoverLetterSelectionEdit');
    expect(api).toContain('applyCoverLetterSelectionEdit');
  });
});
