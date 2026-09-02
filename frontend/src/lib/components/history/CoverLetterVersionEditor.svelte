<script lang="ts">
  import {
    applyCoverLetterSelectionEdit,
    createCoverLetterVersion,
    streamCoverLetterSelectionEdit,
  } from '$lib/api';
  import { Button } from '$lib/components/ui/button';
  import { Textarea } from '$lib/components/ui/textarea';
  import { consumeStream } from '$lib/stream';
  import { toastState } from '$lib/toast.svelte';
  import { errorMessage } from '$lib/utils';
  import type { GeneratedCoverLetterEntry } from '$lib/types';
  import { Loader2, Sparkles } from '@lucide/svelte';

  interface Props {
    selectedCl: GeneratedCoverLetterEntry;
    onSaved: (updated: GeneratedCoverLetterEntry) => void;
    onCancel: () => void;
  }

  let { selectedCl, onSaved, onCancel }: Props = $props();

  let text = $state(selectedCl.cover_letter_text);
  let saving = $state(false);
  let textareaRef = $state<HTMLTextAreaElement | undefined>(undefined);
  let selectionStart = $state(0);
  let selectionEnd = $state(0);
  let instruction = $state('');
  let rewritePreview = $state('');
  let rewriting = $state(false);
  let applyingRewrite = $state(false);

  const dirty = $derived(text !== selectedCl.cover_letter_text);
  const selectedExcerpt = $derived(text.slice(selectionStart, selectionEnd));
  const hasSelection = $derived(selectionEnd > selectionStart);

  function captureSelection() {
    if (!textareaRef) return;
    selectionStart = textareaRef.selectionStart;
    selectionEnd = textareaRef.selectionEnd;
  }

  function resetRewrite() {
    instruction = '';
    rewritePreview = '';
  }

  async function handleSave() {
    if (!dirty) return;
    saving = true;
    try {
      const updated = await createCoverLetterVersion(selectedCl.id, { cover_letter_text: text });
      toastState.success('Saved as a new version.');
      onSaved(updated);
    } catch (e: unknown) {
      toastState.error(`Failed to save: ${errorMessage(e)}`);
    } finally {
      saving = false;
    }
  }

  async function handleRewrite() {
    if (!selectedExcerpt.trim() || !instruction.trim()) return;
    rewriting = true;
    rewritePreview = '';
    try {
      const res = await streamCoverLetterSelectionEdit(selectedCl.id, {
        excerpt: selectedExcerpt,
        instruction,
      });
      if (!res.ok) throw new Error('Generation failed');
      await consumeStream(res, {
        onChunk: (chunk) => { rewritePreview += chunk; },
        onDone: () => {},
        onError: (msg) => toastState.error(msg),
      });
    } catch (e: unknown) {
      toastState.error(`Generation failed: ${errorMessage(e)}`);
    } finally {
      rewriting = false;
    }
  }

  async function handleApplyRewrite() {
    if (!rewritePreview) return;
    applyingRewrite = true;
    try {
      const updated = await applyCoverLetterSelectionEdit(selectedCl.id, {
        selection_start: selectionStart,
        selection_end: selectionEnd,
        excerpt: selectedExcerpt,
        new_value: rewritePreview,
        instruction,
      });
      toastState.success('Excerpt rewritten and saved as a new version.');
      onSaved(updated);
    } catch (e: unknown) {
      toastState.error(`Failed to save: ${errorMessage(e)}`);
    } finally {
      applyingRewrite = false;
    }
  }
</script>

<div class="p-6 md:p-8 max-w-4xl mx-auto space-y-4">
  <div class="bg-card border border-border/60 rounded-xl shadow-sm p-6 sm:p-8 md:p-10 space-y-4">
    <Textarea
      bind:ref={textareaRef}
      bind:value={text}
      onselect={captureSelection}
      onmouseup={captureSelection}
      onkeyup={captureSelection}
      class="min-h-[50vh] font-mono text-sm leading-relaxed"
    />
    <div class="flex items-center justify-end gap-2">
      <Button variant="outline" size="sm" onclick={onCancel} disabled={saving}>Cancel</Button>
      <Button size="sm" onclick={handleSave} disabled={!dirty || saving}>
        {saving ? 'Saving…' : 'Save as new version'}
      </Button>
    </div>
  </div>

  {#if hasSelection}
    <div class="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
      {#if dirty}
        <p class="text-xs text-muted-foreground">
          Save or cancel your other unsaved changes before using AI rewrite on a selection.
        </p>
      {:else}
        <p class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Ask AI to rewrite the selected text
        </p>
        <p class="text-xs italic text-muted-foreground line-clamp-2">"{selectedExcerpt}"</p>
        <input
          bind:value={instruction}
          placeholder="e.g. Make this more concise, or emphasize leadership experience"
          class="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
        />
        <Button
          onclick={handleRewrite}
          disabled={rewriting || !instruction.trim()}
          size="sm"
        >
          {#if rewriting}
            <Loader2 class="w-4 h-4 mr-2 animate-spin" />
            Rewriting…
          {:else}
            <Sparkles class="w-4 h-4 mr-2" />
            Rewrite selection
          {/if}
        </Button>

        {#if rewritePreview || rewriting}
          <div class="space-y-2">
            <p class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Preview</p>
            <div class="min-h-16 p-3 rounded-lg bg-background border border-border text-sm leading-relaxed whitespace-pre-wrap">
              {rewritePreview}{#if rewriting}<span class="inline-block w-1.5 h-4 bg-primary ml-0.5 animate-pulse rounded-sm"></span>{/if}
            </div>
            {#if rewritePreview && !rewriting}
              <div class="flex gap-2">
                <Button onclick={handleApplyRewrite} disabled={applyingRewrite} size="sm" class="flex-1">
                  {applyingRewrite ? 'Saving…' : 'Apply & Save Version'}
                </Button>
                <Button onclick={resetRewrite} variant="outline" size="sm" disabled={applyingRewrite}>
                  Discard
                </Button>
              </div>
            {/if}
          </div>
        {/if}
      {/if}
    </div>
  {/if}
</div>
