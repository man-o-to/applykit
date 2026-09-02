<script lang="ts">
  import {
    compareCoverLetterVersions,
    compareCvVersions,
    getCoverLetterVersions,
    getCvVersions,
    revertCoverLetterVersion,
    revertCvVersion,
  } from '$lib/api';
  import { Badge } from '$lib/components/ui/badge';
  import { Button } from '$lib/components/ui/button';
  import { toastState } from '$lib/toast.svelte';
  import type {
    CoverLetterComparisonResponse,
    CvComparisonResponse,
    DocumentVersionItem,
    GeneratedCVEntry,
    GeneratedCoverLetterEntry,
  } from '$lib/types';
  import { formatDate, errorMessage } from '$lib/utils';
  import { History, RotateCcw } from '@lucide/svelte';

  interface Props {
    documentType: 'cv' | 'cover-letter';
    entryId: number;
    onRestored: (updated: GeneratedCVEntry | GeneratedCoverLetterEntry) => void;
  }

  let { documentType, entryId, onRestored }: Props = $props();

  let versions = $state<DocumentVersionItem[]>([]);
  let loading = $state(true);
  let loadError = $state('');
  let restoringId = $state<number | null>(null);
  let comparingId = $state<number | null>(null);
  let comparisonLoading = $state(false);
  let cvComparison = $state<CvComparisonResponse | null>(null);
  let clComparison = $state<CoverLetterComparisonResponse | null>(null);

  const EDIT_SOURCE_LABELS: Record<string, string> = {
    manual: 'Manual edit',
    ai_selection: 'AI rewrite',
    ai_chat: 'AI chat',
    restore: 'Restored',
  };

  const headVersion = $derived(versions.find((v) => v.superseded_by_id === null) ?? null);

  async function load() {
    loading = true;
    loadError = '';
    try {
      const res =
        documentType === 'cv' ? await getCvVersions(entryId) : await getCoverLetterVersions(entryId);
      versions = res.items;
    } catch (e: unknown) {
      loadError = errorMessage(e);
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    entryId;
    documentType;
    comparingId = null;
    cvComparison = null;
    clComparison = null;
    load();
  });

  async function handleRestore(targetId: number) {
    if (!headVersion) return;
    restoringId = targetId;
    try {
      const updated =
        documentType === 'cv'
          ? await revertCvVersion(headVersion.id, targetId)
          : await revertCoverLetterVersion(headVersion.id, targetId);
      toastState.success('Restored as a new version.');
      onRestored(updated);
    } catch (e: unknown) {
      toastState.error(`Failed to restore: ${errorMessage(e)}`);
    } finally {
      restoringId = null;
    }
  }

  async function toggleCompare(versionId: number) {
    if (comparingId === versionId) {
      comparingId = null;
      return;
    }
    if (!headVersion) return;
    comparingId = versionId;
    comparisonLoading = true;
    cvComparison = null;
    clComparison = null;
    try {
      if (documentType === 'cv') {
        cvComparison = await compareCvVersions(versionId, headVersion.id);
      } else {
        clComparison = await compareCoverLetterVersions(versionId, headVersion.id);
      }
    } catch (e: unknown) {
      toastState.error(`Failed to load comparison: ${errorMessage(e)}`);
      comparingId = null;
    } finally {
      comparisonLoading = false;
    }
  }
</script>

<section class="rounded-2xl border border-border bg-card p-5 shadow-sm">
  <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
    <History class="h-4 w-4 text-primary" aria-hidden="true" />
    Version history
  </h3>

  {#if loading}
    <p class="mt-3 text-xs text-muted-foreground">Loading…</p>
  {:else if loadError}
    <p class="mt-3 text-xs text-destructive">{loadError}</p>
  {:else if versions.length <= 1}
    <p class="mt-3 text-xs text-muted-foreground">No earlier versions yet — edits will show up here.</p>
  {:else}
    <ol class="mt-4 space-y-2">
      {#each versions as version, index}
        {@const isHead = version.superseded_by_id === null}
        <li class="rounded-xl border border-border px-3.5 py-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-xs font-semibold text-foreground">
                Version {index + 1}{#if isHead}<span class="ml-1.5 text-primary">(current)</span>{/if}
              </p>
              <p class="mt-0.5 text-[11px] text-muted-foreground">{formatDate(version.created_at)}</p>
              {#if version.edit_source}
                <Badge variant="secondary" class="mt-1.5">
                  {EDIT_SOURCE_LABELS[version.edit_source] ?? version.edit_source}
                </Badge>
              {/if}
              {#if version.edit_instruction}
                <p class="mt-1.5 text-[11px] text-muted-foreground italic">"{version.edit_instruction}"</p>
              {/if}
            </div>
            {#if !isHead}
              <div class="flex shrink-0 flex-col items-end gap-1.5">
                <Button variant="outline" size="sm" onclick={() => toggleCompare(version.id)}>
                  {comparingId === version.id ? 'Hide diff' : 'Compare to current'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onclick={() => handleRestore(version.id)}
                  disabled={restoringId === version.id}
                >
                  <RotateCcw class="w-3.5 h-3.5 mr-1.5" />
                  {restoringId === version.id ? 'Restoring…' : 'Restore this version'}
                </Button>
              </div>
            {/if}
          </div>

          {#if comparingId === version.id}
            <div class="mt-3 rounded-lg bg-muted/40 p-3 text-xs">
              {#if comparisonLoading}
                <p class="text-muted-foreground">Loading diff…</p>
              {:else if documentType === 'cv' && cvComparison}
                {#if cvComparison.changed_fields.length === 0}
                  <p class="text-muted-foreground">No differences from the current version.</p>
                {:else}
                  <ul class="space-y-1.5 font-mono">
                    {#each cvComparison.changed_fields as change}
                      <li>
                        <span class="font-semibold text-foreground">{change.path}</span>
                        <span class="text-muted-foreground"> changed</span>
                      </li>
                    {/each}
                  </ul>
                {/if}
              {:else if documentType === 'cover-letter' && clComparison}
                {#if clComparison.diff.length === 0}
                  <p class="text-muted-foreground">No differences from the current version.</p>
                {:else}
                  <div class="space-y-1 font-mono whitespace-pre-wrap">
                    {#each clComparison.diff as entry}
                      {#each entry.from_lines as line}
                        <div class="text-destructive">- {line}</div>
                      {/each}
                      {#each entry.to_lines as line}
                        <div class="text-emerald-600 dark:text-emerald-400">+ {line}</div>
                      {/each}
                    {/each}
                  </div>
                {/if}
              {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ol>
  {/if}
</section>
