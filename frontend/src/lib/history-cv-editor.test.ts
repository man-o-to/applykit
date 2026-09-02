import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const editor = readFileSync(
  new URL('./components/history/CvVersionEditor.svelte', import.meta.url),
  'utf8',
);
const experienceTab = readFileSync(
  new URL('./components/profile/ExperienceTab.svelte', import.meta.url),
  'utf8',
);
const personalInfoTab = readFileSync(
  new URL('./components/profile/PersonalInfoTab.svelte', import.meta.url),
  'utf8',
);
const historyPage = readFileSync(new URL('../routes/history/+page.svelte', import.meta.url), 'utf8');
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');

describe('CV manual version editor', () => {
  test('all six profile tabs are wired in', () => {
    for (const tab of [
      'PersonalInfoTab',
      'SkillsTab',
      'ExperienceTab',
      'EducationTab',
      'ProjectsTab',
      'CertificationsTab',
    ]) {
      expect(editor).toContain(tab);
    }
  });

  test('the summary AI tool - not yet retargeted - stays hidden when editing a historical snapshot', () => {
    expect(editor).toContain('hideAiTools={true}');
  });

  test('the experience tab AI bullet tool is retargeted to selection-rewrite, not hidden', () => {
    expect(editor).toContain('onAiRewrite={aiRewrite}');
    expect(editor).not.toContain('hideAiBulletTools={true}');
  });

  test('saving calls createCvVersion, not a status or delete call', () => {
    expect(editor).toContain('createCvVersion');
    expect(editor).not.toContain('deleteCvHistoryEntry');
    expect(editor).not.toContain('updateCvStatus');
  });

  test('api client exposes the CV version endpoints', () => {
    expect(api).toContain("request<GeneratedCVEntry>(`/history/cv/${id}/versions`");
  });

  test('the experience tab AI bullet trigger respects hideAiBulletTools', () => {
    expect(experienceTab).toContain('hideAiBulletTools?: boolean');
    expect(experienceTab).toContain('{#if !hideAiBulletTools}');
  });

  test('the personal info tab AI summary trigger respects hideAiTools', () => {
    expect(personalInfoTab).toContain('hideAiTools?: boolean');
    expect(personalInfoTab).toContain('{#if !hideAiTools}');
  });

  test('the history page swaps in the CV editor and replaces the selected entry on save', () => {
    expect(historyPage).toContain('CvVersionEditor');
    expect(historyPage).toContain('handleCvVersionSaved');
    expect(historyPage).toContain('editingCv');
  });
});
