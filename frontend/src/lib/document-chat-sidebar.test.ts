import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';

const sidebar = readFileSync(
  new URL('./components/history/DocumentChatSidebar.svelte', import.meta.url),
  'utf8',
);
const clHeader = readFileSync(
  new URL('./components/history/ClPreviewHeader.svelte', import.meta.url),
  'utf8',
);
const historyPage = readFileSync(new URL('../routes/history/+page.svelte', import.meta.url), 'utf8');
const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');

describe('document chat sidebar', () => {
  test('uses the event-name-aware stream consumer, not the payload-shape one', () => {
    expect(sidebar).toContain('consumeStructuredStream');
    expect(sidebar).not.toContain('consumeStream(');
  });

  test('input is disabled while a turn is streaming', () => {
    expect(sidebar).toContain('sending ||');
    expect(sidebar).toContain('disabled={inputDisabled}');
  });

  test('input is disabled while a patch is pending apply or discard', () => {
    expect(sidebar).toContain('pendingMessage !== null');
    expect(sidebar).toContain('applyingMessageId !== null');
  });

  test('input is disabled once the session turn cap is reached', () => {
    expect(sidebar).toContain('capReached');
    expect(sidebar).toContain('MAX_TURNS_PER_SESSION');
  });

  test('a pending patch renders Apply and Discard actions, applying calls onApplied', () => {
    expect(sidebar).toContain('Apply');
    expect(sidebar).toContain('Discard');
    expect(sidebar).toContain('applyPatch(message.id)');
    expect(sidebar).toContain('discardPatch(message.id)');
    expect(sidebar).toContain('onApplied(updated)');
  });

  test('nothing is applied without the explicit Apply action - discard never calls onApplied', () => {
    const discardFn = sidebar.slice(
      sidebar.indexOf('async function discardPatch'),
      sidebar.indexOf('function patchSummary'),
    );
    expect(discardFn).not.toContain('onApplied');
  });

  test('api client exposes the chat session, turn-stream, and patch action endpoints for both document types', () => {
    expect(api).toContain('createCvChatSession');
    expect(api).toContain('streamCvChatTurn');
    expect(api).toContain('applyCvChatPatch');
    expect(api).toContain('discardCvChatPatch');
    expect(api).toContain('createCoverLetterChatSession');
    expect(api).toContain('streamCoverLetterChatTurn');
    expect(api).toContain('applyCoverLetterChatPatch');
    expect(api).toContain('discardCoverLetterChatPatch');
  });

  test('the cover letter header and the history page wire an AI Chat toggle', () => {
    expect(clHeader).toContain('onToggleChat');
    expect(historyPage).toContain('DocumentChatSidebar');
    expect(historyPage).toContain('showCvChat');
    expect(historyPage).toContain('showClChat');
  });
});
