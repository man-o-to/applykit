<script lang="ts">
  import { createCoverLetterVersion } from '$lib/api';
  import { Button } from '$lib/components/ui/button';
  import { Textarea } from '$lib/components/ui/textarea';
  import { toastState } from '$lib/toast.svelte';
  import { errorMessage } from '$lib/utils';
  import type { GeneratedCoverLetterEntry } from '$lib/types';

  interface Props {
    selectedCl: GeneratedCoverLetterEntry;
    onSaved: (updated: GeneratedCoverLetterEntry) => void;
    onCancel: () => void;
  }

  let { selectedCl, onSaved, onCancel }: Props = $props();

  let text = $state(selectedCl.cover_letter_text);
  let saving = $state(false);

  const dirty = $derived(text !== selectedCl.cover_letter_text);

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
</script>

<div class="p-6 md:p-8 max-w-4xl mx-auto">
  <div class="bg-card border border-border/60 rounded-xl shadow-sm p-6 sm:p-8 md:p-10 space-y-4">
    <Textarea bind:value={text} class="min-h-[50vh] font-mono text-sm leading-relaxed" />
    <div class="flex items-center justify-end gap-2">
      <Button variant="outline" size="sm" onclick={onCancel} disabled={saving}>Cancel</Button>
      <Button size="sm" onclick={handleSave} disabled={!dirty || saving}>
        {saving ? 'Saving…' : 'Save as new version'}
      </Button>
    </div>
  </div>
</div>
