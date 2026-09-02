<script lang="ts">
  import { createCvVersion } from '$lib/api';
  import CertificationsTab from '$lib/components/profile/CertificationsTab.svelte';
  import EducationTab from '$lib/components/profile/EducationTab.svelte';
  import ExperienceTab from '$lib/components/profile/ExperienceTab.svelte';
  import PersonalInfoTab from '$lib/components/profile/PersonalInfoTab.svelte';
  import ProjectsTab from '$lib/components/profile/ProjectsTab.svelte';
  import SkillsTab from '$lib/components/profile/SkillsTab.svelte';
  import { Button } from '$lib/components/ui/button';
  import { toastState } from '$lib/toast.svelte';
  import type { GeneratedCVEntry, ProfileData } from '$lib/types';
  import { errorMessage } from '$lib/utils';
  import { Award, Building2, FolderGit2, GraduationCap, User } from '@lucide/svelte';

  interface Props {
    selectedCv: GeneratedCVEntry;
    initialProfile: ProfileData;
    onSaved: (updated: GeneratedCVEntry) => void;
    onCancel: () => void;
  }

  let { selectedCv, initialProfile, onSaved, onCancel }: Props = $props();

  const loadedJson = initialProfile ? JSON.stringify(initialProfile) : '';
  let profile: ProfileData = $state(structuredClone(initialProfile));
  let activeTab = $state('personal-info');
  let saving = $state(false);

  const dirty = $derived(JSON.stringify(profile) !== loadedJson);

  const sections = [
    { id: 'personal-info', label: 'Personal Info', icon: User },
    { id: 'skills', label: 'Core Skills', icon: Award },
    { id: 'experience', label: 'Experience', icon: Building2 },
    { id: 'education', label: 'Education', icon: GraduationCap },
    { id: 'projects', label: 'Projects', icon: FolderGit2 },
    { id: 'certifications', label: 'Certifications & Training', icon: Award },
  ];

  async function handleSave() {
    if (!dirty) return;
    saving = true;
    try {
      const updated = await createCvVersion(selectedCv.id, { profile_snapshot: profile });
      toastState.success('Saved as a new version.');
      onSaved(updated);
    } catch (e: unknown) {
      toastState.error(`Failed to save: ${errorMessage(e)}`);
    } finally {
      saving = false;
    }
  }
</script>

<div class="p-4 md:p-6 space-y-4">
  <div class="flex overflow-x-auto pb-1 gap-2 no-scrollbar">
    {#each sections as section}
      <button
        type="button"
        onclick={() => activeTab = section.id}
        class="whitespace-nowrap flex items-center gap-2 px-4 py-2 rounded-full border transition-all text-sm
               {activeTab === section.id
                 ? 'bg-primary text-primary-foreground border-primary shadow-sm font-semibold'
                 : 'bg-muted/50 text-muted-foreground border-transparent hover:bg-muted hover:text-foreground'}"
      >
        <section.icon class="w-4 h-4" />
        {section.label}
      </button>
    {/each}
  </div>

  <div class="bg-card border border-border/60 rounded-xl shadow-sm">
    {#if activeTab === 'personal-info'}
      <section class="p-6"><PersonalInfoTab bind:profile hideAiTools={true} /></section>
    {/if}
    {#if activeTab === 'skills'}
      <section class="p-6"><SkillsTab bind:profile /></section>
    {/if}
    {#if activeTab === 'experience'}
      <section class="p-6"><ExperienceTab bind:profile hideAiBulletTools={true} /></section>
    {/if}
    {#if activeTab === 'education'}
      <section class="p-6"><EducationTab bind:profile /></section>
    {/if}
    {#if activeTab === 'projects'}
      <section class="p-6"><ProjectsTab bind:profile /></section>
    {/if}
    {#if activeTab === 'certifications'}
      <section class="p-6"><CertificationsTab bind:profile /></section>
    {/if}
  </div>

  <div class="flex items-center justify-end gap-2">
    <Button variant="outline" size="sm" onclick={onCancel} disabled={saving}>Cancel</Button>
    <Button size="sm" onclick={handleSave} disabled={!dirty || saving}>
      {saving ? 'Saving…' : 'Save as new version'}
    </Button>
  </div>
</div>
