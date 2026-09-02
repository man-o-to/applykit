import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const editor = readFileSync(
  new URL('./components/history/CoverLetterVersionEditor.svelte', import.meta.url),
  'utf8',
);
const header = readFileSync(
  new URL('./components/history/ClPreviewHeader.svelte', import.meta.url),
  'utf8',
);
const historyPage = readFileSync(new URL('../routes/history/+page.svelte', import.meta.url), 'utf8');
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');

describe('cover letter manual version editor', () => {
  test('saving calls createCoverLetterVersion, not a status or delete call', () => {
    expect(editor).toContain('createCoverLetterVersion');
    expect(editor).not.toContain('updateCoverLetterStatus');
    expect(editor).not.toContain('deleteCoverLetterHistoryEntry');
  });

  test('api client exposes the version endpoints for both document types', () => {
    expect(api).toContain("request<GeneratedCoverLetterEntry>(`/history/cover-letter/${id}/versions`");
    expect(api).toContain("request<GeneratedCVEntry>(`/history/cv/${id}/versions`");
    expect(api).toContain('/versions/${targetId}/revert');
  });

  test('the edit toggle is wired into the cover letter preview header', () => {
    expect(header).toContain('onToggleEdit');
    expect(header).toContain('editing');
  });

  test('the history page swaps in the editor and replaces the selected entry on save', () => {
    expect(historyPage).toContain('CoverLetterVersionEditor');
    expect(historyPage).toContain('handleClVersionSaved');
    expect(historyPage).toContain('editingCl');
  });
});
