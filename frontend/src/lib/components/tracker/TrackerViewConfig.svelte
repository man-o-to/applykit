<script lang="ts">
	import { Popover, PopoverContent, PopoverTrigger } from '$lib/components/ui/popover';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import {
		ALL_COLUMNS,
		ALL_CARD_FIELDS,
		GROUP_BY_OPTIONS,
		type TrackerViewConfigState
	} from '$lib/tracker-view-config';
	import { Settings, ChevronUp, ChevronDown, FileDown, Download } from '@lucide/svelte';
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

	let columnItems = $derived(
		config.columnOrder.map((key) => ({ id: key, label: labelByKey.get(key) ?? key }))
	);

	// Plain move-up/move-down instead of drag-and-drop: svelte-dnd-action
	// positions its dragged clone with `position: fixed` computed from the
	// viewport, but this popover is positioned via a CSS transform (bits-ui's
	// floating-ui anchoring) — any transformed ancestor becomes the containing
	// block for a fixed descendant, so the dragged clone renders in the wrong
	// place instead of near the cursor. Buttons sidestep that entirely.
	function moveColumn(index: number, direction: -1 | 1) {
		const target = index + direction;
		if (target < 0 || target >= config.columnOrder.length) return;
		const next = [...config.columnOrder];
		[next[index], next[target]] = [next[target], next[index]];
		config.columnOrder = next;
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
					<div class="space-y-0.5">
						{#each columnItems as col, i (col.id)}
							<div class="flex items-center gap-1.5 px-1 py-1 rounded hover:bg-accent/50">
								<div class="flex flex-col -my-0.5 shrink-0">
									<button
										type="button"
										disabled={i === 0}
										onclick={() => moveColumn(i, -1)}
										aria-label="Move {col.label} up"
										class="text-muted-foreground/50 hover:text-foreground disabled:opacity-30 disabled:hover:text-muted-foreground/50"
									>
										<ChevronUp class="w-3 h-3" />
									</button>
									<button
										type="button"
										disabled={i === columnItems.length - 1}
										onclick={() => moveColumn(i, 1)}
										aria-label="Move {col.label} down"
										class="text-muted-foreground/50 hover:text-foreground disabled:opacity-30 disabled:hover:text-muted-foreground/50"
									>
										<ChevronDown class="w-3 h-3" />
									</button>
								</div>
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
