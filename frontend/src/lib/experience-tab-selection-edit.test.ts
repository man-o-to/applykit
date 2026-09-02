import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const experienceTab = readFileSync(
  new URL('./components/profile/ExperienceTab.svelte', import.meta.url),
  'utf8',
);
const cvEditor = readFileSync(
  new URL('./components/history/CvVersionEditor.svelte', import.meta.url),
  'utf8',
);
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');

describe('experience tab selection-rewrite retargeting', () => {
  test('accepts an onAiRewrite handler distinct from the plain hide flag', () => {
    expect(experienceTab).toContain('onAiRewrite?: AiRewriteHandler');
  });

  test('generateBullets calls the retargeted stream when onAiRewrite is supplied, not generateBulletsStream against the live profile', () => {
    expect(experienceTab).toContain('res = await onAiRewrite.stream(i, lastInstruction);');
    expect(experienceTab).toContain('res = await generateBulletsStream(');
    // Both paths exist, but they're mutually exclusive behind the same `if (onAiRewrite)` branch.
    const ifIndex = experienceTab.indexOf('if (onAiRewrite) {');
    const streamIndex = experienceTab.indexOf('res = await onAiRewrite.stream');
    const fallbackIndex = experienceTab.indexOf('res = await generateBulletsStream(');
    expect(ifIndex).toBeGreaterThan(-1);
    expect(streamIndex).toBeGreaterThan(ifIndex);
    expect(fallbackIndex).toBeGreaterThan(streamIndex);
  });

  test('applyBullets persists via onAiRewrite.apply instead of a local-only buffer update when supplied', () => {
    expect(experienceTab).toContain('await onAiRewrite.apply(i, lines, lastInstruction);');
  });

  test('the AI Enhance trigger is disabled with a reason when the handler reports disabled', () => {
    expect(experienceTab).toContain('disabled={onAiRewrite?.disabled}');
    expect(experienceTab).toContain('onAiRewrite.disabledReason');
  });
});

describe('CV editor selection-rewrite wiring', () => {
  test('gates AI rewrite on unsaved local changes so it can never silently discard them', () => {
    expect(cvEditor).toContain('disabled: dirty,');
  });

  test('AI-applied rewrites close the editor the same way the main save does', () => {
    expect(cvEditor).toContain('onSaved(updated);');
  });

  test('api client exposes the CV selection-edit endpoints', () => {
    expect(api).toContain('streamCvSelectionEdit');
    expect(api).toContain('applyCvSelectionEdit');
    expect(api).toContain('/edit/selection/stream');
    expect(api).toContain('/edit/selection/apply');
  });
});
