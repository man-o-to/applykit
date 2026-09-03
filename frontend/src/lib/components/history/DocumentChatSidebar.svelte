<script lang="ts">
  import {
    applyCoverLetterChatPatch,
    applyCvChatPatch,
    createCoverLetterChatSession,
    createCvChatSession,
    discardCoverLetterChatPatch,
    discardCvChatPatch,
    getCoverLetterChatMessages,
    getCvChatMessages,
    streamCoverLetterChatTurn,
    streamCvChatTurn,
  } from '$lib/api';
  import { Button } from '$lib/components/ui/button';
  import { Textarea } from '$lib/components/ui/textarea';
  import { consumeStructuredStream } from '$lib/stream';
  import { toastState } from '$lib/toast.svelte';
  import type {
    ChatMessageItem,
    ChatSessionResponse,
    CoverLetterChatPatch,
    CvChatPatch,
    GeneratedCVEntry,
    GeneratedCoverLetterEntry,
  } from '$lib/types';
  import { errorMessage } from '$lib/utils';
  import { Check, Loader2, MessageCircle, Send, X } from '@lucide/svelte';

  // Mirrors the backend's MAX_TURNS_PER_SESSION (app/history_chat/repository.py).
  const MAX_TURNS_PER_SESSION = 20;

  interface Props {
    documentType: 'cv' | 'cover-letter';
    entryId: number;
    onApplied: (updated: GeneratedCVEntry | GeneratedCoverLetterEntry) => void;
    onClose: () => void;
  }

  let { documentType, entryId, onApplied, onClose }: Props = $props();

  let session = $state<ChatSessionResponse | null>(null);
  let messages = $state<ChatMessageItem[]>([]);
  let starting = $state(false);
  let sending = $state(false);
  let input = $state('');
  let streamingReply = $state('');
  let applyingMessageId = $state<number | null>(null);
  let scrollEl = $state<HTMLDivElement | undefined>(undefined);

  const pendingMessage = $derived(messages.find((m) => m.patch_status === 'pending') ?? null);
  const capReached = $derived((session?.turn_count ?? 0) >= MAX_TURNS_PER_SESSION);
  const inputDisabled = $derived(
    !session || sending || pendingMessage !== null || applyingMessageId !== null || capReached,
  );

  $effect(() => {
    entryId;
    documentType;
    session = null;
    messages = [];
    streamingReply = '';
    startSession();
  });

  $effect(() => {
    messages.length;
    streamingReply;
    scrollEl?.scrollTo({ top: scrollEl.scrollHeight, behavior: 'smooth' });
  });

  async function startSession() {
    starting = true;
    try {
      session =
        documentType === 'cv'
          ? await createCvChatSession(entryId)
          : await createCoverLetterChatSession(entryId);
    } catch (e: unknown) {
      toastState.error(`Failed to start chat: ${errorMessage(e)}`);
    } finally {
      starting = false;
    }
  }

  async function reloadMessages() {
    if (!session) return;
    const res =
      documentType === 'cv'
        ? await getCvChatMessages(session.id)
        : await getCoverLetterChatMessages(session.id);
    messages = res.items;
  }

  async function sendMessage() {
    if (!session || inputDisabled) return;
    const content = input.trim();
    if (!content) return;
    input = '';
    sending = true;
    streamingReply = '';
    let latestTurnCount: number | null = null;

    const optimisticUser: ChatMessageItem = {
      id: -1,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      proposed_patch: null,
      patch_status: null,
      resulting_version_id: null,
    };
    messages = [...messages, optimisticUser];

    try {
      const res =
        documentType === 'cv'
          ? await streamCvChatTurn(session.id, { content })
          : await streamCoverLetterChatTurn(session.id, { content });
      if (!res.ok) throw new Error('The chat request failed.');
      await consumeStructuredStream(res, {
        onEvent(event, data) {
          if (event === 'token') {
            streamingReply += data as string;
          } else if (event === 'done') {
            latestTurnCount = (data as { turn_count: number }).turn_count;
          }
        },
        onError(msg) {
          toastState.error(msg);
        },
      });
      await reloadMessages();
      if (session && latestTurnCount !== null) {
        session = { ...session, turn_count: latestTurnCount };
      }
    } catch (e: unknown) {
      toastState.error(`Failed to send message: ${errorMessage(e)}`);
      messages = messages.filter((m) => m !== optimisticUser);
    } finally {
      sending = false;
      streamingReply = '';
    }
  }

  async function applyPatch(messageId: number) {
    if (!session) return;
    applyingMessageId = messageId;
    try {
      const updated =
        documentType === 'cv'
          ? await applyCvChatPatch(session.id, messageId)
          : await applyCoverLetterChatPatch(session.id, messageId);
      toastState.success('Applied — saved as a new version.');
      onApplied(updated);
      await reloadMessages();
    } catch (e: unknown) {
      toastState.error(`Failed to apply: ${errorMessage(e)}`);
    } finally {
      applyingMessageId = null;
    }
  }

  async function discardPatch(messageId: number) {
    if (!session) return;
    applyingMessageId = messageId;
    try {
      if (documentType === 'cv') {
        await discardCvChatPatch(session.id, messageId);
      } else {
        await discardCoverLetterChatPatch(session.id, messageId);
      }
      await reloadMessages();
    } catch (e: unknown) {
      toastState.error(`Failed to discard: ${errorMessage(e)}`);
    } finally {
      applyingMessageId = null;
    }
  }

  function patchSummary(patch: CvChatPatch | CoverLetterChatPatch): { label: string; preview: string } {
    if ('target' in patch) {
      const target = patch.target;
      const label =
        target.section === 'summary'
          ? 'Summary'
          : `${target.section.replaceAll('_', ' ')}${target.index != null ? ` #${target.index + 1}` : ''}${target.subfield ? ` · ${target.subfield}` : ''}`;
      const preview = Array.isArray(patch.new_value)
        ? patch.new_value.join('\n')
        : String(patch.new_value);
      return { label, preview };
    }
    return { label: 'Full letter rewrite', preview: patch.new_value };
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }
</script>

<div class="flex h-full flex-col border-l border-border bg-card">
  <div class="flex items-center justify-between gap-2 border-b border-border p-3">
    <div class="flex items-center gap-2 text-sm font-semibold text-foreground">
      <MessageCircle class="h-4 w-4 text-primary" aria-hidden="true" />
      AI chat
    </div>
    <button
      onclick={onClose}
      class="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
      title="Close chat"
      aria-label="Close chat"
    >
      <X class="h-4 w-4" />
    </button>
  </div>

  <div bind:this={scrollEl} class="flex-1 space-y-3 overflow-y-auto p-3">
    {#if starting}
      <p class="text-xs text-muted-foreground">Starting session…</p>
    {:else if messages.length === 0}
      <p class="text-xs text-muted-foreground">
        Ask for changes in plain language. Proposed edits show up here for you to review before
        anything is saved.
      </p>
    {/if}

    {#each messages as message (message.id)}
      <div class="flex flex-col gap-1 {message.role === 'user' ? 'items-end' : 'items-start'}">
        <div
          class="max-w-[85%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap
            {message.role === 'user'
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-foreground'}"
        >
          {message.content}
        </div>

        {#if message.proposed_patch}
          {@const summary = patchSummary(message.proposed_patch)}
          <div class="w-full max-w-[85%] rounded-xl border border-primary/20 bg-primary/5 p-3">
            <p class="text-[10px] font-bold uppercase tracking-widest text-primary">
              Proposed edit · {summary.label}
            </p>
            <p class="mt-1.5 max-h-32 overflow-y-auto whitespace-pre-wrap text-xs text-foreground">
              {summary.preview}
            </p>
            {#if message.patch_status === 'pending'}
              <div class="mt-2.5 flex gap-2">
                <Button
                  size="sm"
                  disabled={applyingMessageId === message.id}
                  onclick={() => applyPatch(message.id)}
                >
                  {#if applyingMessageId === message.id}
                    <Loader2 class="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  {:else}
                    <Check class="h-3.5 w-3.5 mr-1.5" />
                  {/if}
                  Apply
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={applyingMessageId === message.id}
                  onclick={() => discardPatch(message.id)}
                >
                  Discard
                </Button>
              </div>
            {:else}
              <p class="mt-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                {message.patch_status === 'applied' ? '✓ Applied' : 'Discarded'}
              </p>
            {/if}
          </div>
        {/if}
      </div>
    {/each}

    {#if sending}
      <div class="flex items-start">
        <div class="max-w-[85%] rounded-2xl bg-muted px-3.5 py-2 text-sm whitespace-pre-wrap text-foreground">
          {streamingReply}<span class="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-foreground/60"></span>
        </div>
      </div>
    {/if}
  </div>

  <div class="border-t border-border p-3">
    {#if capReached}
      <p class="mb-2 text-xs text-muted-foreground">
        This chat session has reached its turn limit. Close and reopen to start a new session.
      </p>
    {:else if pendingMessage}
      <p class="mb-2 text-xs text-muted-foreground">
        Apply or discard the proposed edit above before sending another message.
      </p>
    {/if}
    <div class="flex items-end gap-2">
      <Textarea
        bind:value={input}
        onkeydown={handleKeydown}
        disabled={inputDisabled}
        placeholder="Ask for a change…"
        rows={2}
        class="min-h-0 resize-none text-sm"
      />
      <Button size="icon" disabled={inputDisabled || !input.trim()} onclick={sendMessage}>
        <Send class="h-4 w-4" />
      </Button>
    </div>
  </div>
</div>
