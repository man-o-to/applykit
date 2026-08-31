<script lang="ts">
	import { page } from '$app/state';
	import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '$lib/components/ui/tooltip';
	import { LayoutDashboard, Mail, FileUser, Zap, Clock, Briefcase } from '@lucide/svelte';

	const NAV_ITEMS = [
		{ href: '/', label: 'Dashboard', icon: LayoutDashboard },
		{ href: '/cover-letter', label: 'Cover Letter', icon: Mail },
		{ href: '/generate', label: 'Generate CV', icon: FileUser },
		{ href: '/smart-apply', label: 'Smart Apply', icon: Zap },
		{ href: '/history', label: 'History', icon: Clock },
		{ href: '/tracker', label: 'Tracker', icon: Briefcase }
	];

	function isActive(href: string): boolean {
		return page.url.pathname === href;
	}
</script>

<aside
	class="hidden md:flex flex-col items-center w-14 shrink-0 border-r border-border bg-card py-3 gap-1 sticky top-0 h-screen overflow-y-auto"
>
	<TooltipProvider delayDuration={200}>
		{#each NAV_ITEMS as item (item.href)}
			<Tooltip>
				<TooltipTrigger>
					{#snippet child({ props })}
						<a
							{...props}
							href={item.href}
							aria-label={item.label}
							aria-current={isActive(item.href) ? 'page' : undefined}
							class="flex items-center justify-center w-10 h-10 rounded-md transition-colors {isActive(item.href)
								? 'bg-accent text-accent-foreground'
								: 'text-muted-foreground hover:text-foreground hover:bg-accent/50'}"
						>
							<item.icon class="w-5 h-5" />
						</a>
					{/snippet}
				</TooltipTrigger>
				<TooltipContent side="right">{item.label}</TooltipContent>
			</Tooltip>
		{/each}
	</TooltipProvider>
</aside>

<!-- Mobile fallback: a bottom tab bar, since hover tooltips don't translate to touch -->
<nav
	class="md:hidden fixed bottom-0 inset-x-0 z-50 flex items-center justify-around border-t border-border bg-card py-1.5"
>
	{#each NAV_ITEMS as item (item.href)}
		<a
			href={item.href}
			aria-label={item.label}
			aria-current={isActive(item.href) ? 'page' : undefined}
			class="flex flex-col items-center gap-0.5 px-2 py-1 rounded-md text-[10px] font-medium transition-colors {isActive(item.href)
				? 'text-accent-foreground'
				: 'text-muted-foreground'}"
		>
			<item.icon class="w-5 h-5" />
			{item.label}
		</a>
	{/each}
</nav>
