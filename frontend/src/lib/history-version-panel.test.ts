import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const panel = readFileSync(
  new URL('./components/history/DocumentVersionPanel.svelte', import.meta.url),
  'utf8',
);
const historyPage = readFileSync(new URL('../routes/history/+page.svelte', import.meta.url), 'utf8');
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');

describe('document version panel', () => {
  test('renders a restore action for non-head versions', () => {
    expect(panel).toContain('Restore this version');
    expect(panel).toContain('handleRestore');
  });

  test('renders edit_source badges', () => {
    expect(panel).toContain('EDIT_SOURCE_LABELS');
    expect(panel).toContain("manual: 'Manual edit'");
    expect(panel).toContain("ai_chat: 'AI chat'");
    expect(panel).toContain("restore: 'Restored'");
  });

  test('supports comparing a version against the current head', () => {
    expect(panel).toContain('compareCvVersions');
    expect(panel).toContain('compareCoverLetterVersions');
    expect(panel).toContain('Compare to current');
  });

  test('restore calls the compare-safe revert endpoints, not delete', () => {
    expect(panel).toContain('revertCvVersion');
    expect(panel).toContain('revertCoverLetterVersion');
    expect(panel).not.toContain('deleteCvHistoryEntry');
    expect(panel).not.toContain('deleteCoverLetterHistoryEntry');
  });

  test('api client exposes the compare endpoints', () => {
    expect(api).toContain("request<CvComparisonResponse>(`/history/cv/${id}/compare/${otherId}`)");
    expect(api).toContain(
      "request<CoverLetterComparisonResponse>(`/history/cover-letter/${id}/compare/${otherId}`)",
    );
  });

  test('the history page wires a version history toggle for both document types', () => {
    expect(historyPage).toContain('DocumentVersionPanel');
    expect(historyPage).toContain('showCvVersionHistory');
    expect(historyPage).toContain('showClVersionHistory');
    expect(historyPage).toContain('documentType="cv"');
    expect(historyPage).toContain('documentType="cover-letter"');
  });
});
