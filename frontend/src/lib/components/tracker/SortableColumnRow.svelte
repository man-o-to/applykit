<script lang="ts">
	import { createSortable } from '@dnd-kit/svelte/sortable';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { GripVertical } from '@lucide/svelte';
	import type { ApplicationSortColumn } from '$lib/tracker-sort';

	let {
		id,
		index,
		label,
		checked,
		onToggle
	}: {
		id: ApplicationSortColumn;
		index: number;
		label: string;
		checked: boolean;
		onToggle: () => void;
	} = $props();

	const sortable = createSortable({
		get id() {
			return id;
		},
		get index() {
			return index;
		}
	});
</script>

<div {@attach sortable.attach} class="flex items-center gap-1.5 px-1 py-1 rounded hover:bg-accent/50">
	<GripVertical class="w-3.5 h-3.5 text-muted-foreground/40 shrink-0 cursor-grab" />
	<Checkbox id="col-{id}" {checked} onCheckedChange={onToggle} />
	<label for="col-{id}" class="text-xs cursor-pointer select-none">{label}</label>
</div>
