<script lang="ts">
	import { Popover, PopoverContent, PopoverTrigger } from '$lib/components/ui/popover';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import {
		ALL_COLUMNS,
		ALL_CARD_FIELDS,
		GROUP_BY_OPTIONS,
		type TrackerViewConfigState
	} from '$lib/tracker-view-config';
	import { dndzone } from 'svelte-dnd-action';
	import { flip } from 'svelte/animate';
	import { Settings, GripVertical, FileDown, Download } from '@lucide/svelte';
	import type { ApplicationSortColumn } from '$lib/tracker-sort';

	let {
		viewMode,
		config = $bindable(),
		onExport
	}: {
		viewMode: 'board' | 'list';
		config: TrackerViewConfigState;
		onExport: () => void;
	} = $props();

	const labelByKey = new Map(ALL_COLUMNS.map((c) => [c.key, c.label]));

	// dndzone needs a stable `id` field per item; the column key already is one.
	let columnItems = $derived(
		config.columnOrder.map((key) => ({ id: key, label: labelByKey.get(key) ?? key }))
	);

	function handleColumnsDnd(e: CustomEvent<{ items: { id: ApplicationSortColumn; label: string }[] }>) {
		config.columnOrder = e.detail.items.map((i) => i.id);
	}

	function toggleColumn(key: ApplicationSortColumn) {
		config.hiddenColumns = config.hiddenColumns.includes(key)
			? config.hiddenColumns.filter((k) => k !== key)
			: [...config.hiddenColumns, key];
	}

	function toggleCardField(key: (typeof ALL_CARD_FIELDS)[number]['key']) {
		config.hiddenCardFields = config.hiddenCardFields.includes(key)
			? config.hiddenCardFields.filter((k) => k !== key)
			: [...config.hiddenCardFields, key];
	}
</script>

<Popover>
	<PopoverTrigger
		class="p-1.5 rounded border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
		title="View settings"
	>
		<Settings class="w-4 h-4" />
	</PopoverTrigger>
	<PopoverContent class="w-80 p-0" align="end">
		<div class="max-h-[70vh] overflow-y-auto p-3 space-y-4">
			{#if viewMode === 'list'}
				<div>
					<h3 class="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-2">Display</h3>
					<p class="text-xs font-semibold text-foreground mb-1.5">Columns</p>
					<div
						class="space-y-0.5"
						use:dndzone={{ items: columnItems, flipDurationMs: 150, type: 'tracker-columns' }}
						onconsider={handleColumnsDnd}
						onfinalize={handleColumnsDnd}
					>
						{#each columnItems as col (col.id)}
							<div animate:flip={{ duration: 150 }} class="flex items-center gap-2 px-1 py-1 rounded hover:bg-accent/50">
								<GripVertical class="w-3.5 h-3.5 text-muted-foreground/40 shrink-0 cursor-grab" />
								<Checkbox
									id="col-{col.id}"
									checked={!config.hiddenColumns.includes(col.id)}
									onCheckedChange={() => toggleColumn(col.id)}
								/>
								<label for="col-{col.id}" class="text-xs cursor-pointer select-none">{col.label}</label>
							</div>
						{/each}
					</div>

					<p class="text-xs font-semibold text-foreground mt-3 mb-1.5">Group By</p>
					<select
						bind:value={config.groupBy}
						class="w-full bg-background border border-border rounded-md px-2 py-1.5 text-xs"
					>
						{#each GROUP_BY_OPTIONS as opt}
							<option value={opt.value}>{opt.label}</option>
						{/each}
					</select>
				</div>
			{:else}
				<div>
					<h3 class="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-2">Display</h3>
					<p class="text-xs font-semibold text-foreground mb-1.5">Content Display</p>
					<div class="space-y-0.5">
						{#each ALL_CARD_FIELDS as field (field.key)}
							<div class="flex items-center gap-2 px-1 py-1 rounded hover:bg-accent/50">
								<Checkbox
									id="card-{field.key}"
									checked={!config.hiddenCardFields.includes(field.key)}
									onCheckedChange={() => toggleCardField(field.key)}
								/>
								<label for="card-{field.key}" class="text-xs cursor-pointer select-none">{field.label}</label>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<div>
				<h3 class="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-2">Data and reports</h3>
				<div class="space-y-1">
					<button
						type="button"
						onclick={onExport}
						class="w-full flex items-center gap-2 px-2 py-1.5 text-xs rounded hover:bg-accent transition-colors text-left"
					>
						<FileDown class="w-3.5 h-3.5 text-muted-foreground" /> Export Report
					</button>
					<button
						type="button"
						onclick={onExport}
						class="w-full flex items-center gap-2 px-2 py-1.5 text-xs rounded hover:bg-accent transition-colors text-left"
					>
						<Download class="w-3.5 h-3.5 text-muted-foreground" /> Download Data
					</button>
				</div>
			</div>
		</div>
	</PopoverContent>
</Popover>
