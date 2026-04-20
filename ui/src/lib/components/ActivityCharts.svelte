<script lang="ts">
	import type { Snippet } from 'svelte';
	import { barPct, maxVal } from '$lib/format';

	export interface ErrorDetail {
		tool: string;
		message: string;
		count: number;
	}

	let showAllPatterns = $state(false);
	const patternLimit = 6;

	let {
		toolDistribution = {},
		languageDistribution = {},
		timeOfDay = {},
		errorTypes = {},
		errorDetails = undefined,
		insightLabels = undefined,
		extra = undefined,
	}: {
		toolDistribution?: Record<string, number>;
		languageDistribution?: Record<string, number>;
		timeOfDay?: Record<string, number>;
		errorTypes?: Record<string, number>;
		errorDetails?: ErrorDetail[];
		insightLabels?: Record<string, number> | null;
		extra?: Snippet;
	} = $props();

	let patternsSorted = $derived(
		Object.entries(insightLabels ?? {})
			.sort((a, b) => b[1] - a[1])
			.filter(([, c]) => c > 1)
	);
	let patternsMax = $derived(patternsSorted[0]?.[1] ?? 1);
</script>

<div class="chart-bento">
	<div class="chart-box chart-wide">
		<h3>Tools</h3>
		<div class="hbars">
			{#each Object.entries(toolDistribution).slice(0, 8) as [name, count]}
				{@const pct = barPct(count, maxVal(toolDistribution))}
				<div class="hbar">
					<span class="hbar-name">{name}</span>
					<div class="hbar-track"><div class="hbar-fill hbar-c1" style="width:{pct}%"></div></div>
					<span class="hbar-val">{count}</span>
				</div>
			{/each}
			{#if Object.keys(toolDistribution).length === 0}
				<span class="chart-empty">No data</span>
			{/if}
		</div>
	</div>
	<div class="chart-box">
		<h3>Languages</h3>
		<div class="hbars">
			{#each Object.entries(languageDistribution).slice(0, 6) as [lang, count]}
				{@const pct = barPct(count, maxVal(languageDistribution))}
				<div class="hbar">
					<span class="hbar-name">{lang}</span>
					<div class="hbar-track"><div class="hbar-fill hbar-c2" style="width:{pct}%"></div></div>
					<span class="hbar-val">{count}</span>
				</div>
			{/each}
			{#if Object.keys(languageDistribution).length === 0}
				<span class="chart-empty">No data</span>
			{/if}
		</div>
	</div>
	<div class="chart-box">
		<h3>Coding hours</h3>
		<div class="hour-bars">
			{#each Object.entries(timeOfDay) as [hour, count]}
				{@const pct = barPct(count, maxVal(timeOfDay))}
				<div class="hour-col" title="{hour}:00 — {count} sessions">
					<div class="hour-fill" style="height:{pct}%"></div>
					<span class="hour-label">{hour}</span>
				</div>
			{/each}
			{#if Object.keys(timeOfDay).length === 0}
				<span class="chart-empty">No data</span>
			{/if}
		</div>
	</div>
	<div class="chart-box" class:chart-wide={errorDetails && errorDetails.length > 0}>
		<h3>Errors</h3>
		{#if errorDetails && errorDetails.length > 0}
			<div class="error-details">
				{#each errorDetails as err}
					<div class="error-card">
						<div class="error-card-head">
							<span class="error-tool">{err.tool}</span>
							{#if err.count > 1}<span class="error-count">{err.count}x</span>{/if}
						</div>
						<div class="error-msg">{err.message}</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="hbars">
				{#each Object.entries(errorTypes).slice(0, 5) as [type, count]}
					{@const pct = barPct(count, maxVal(errorTypes))}
					<div class="hbar">
						<span class="hbar-name">{type}</span>
						<div class="hbar-track"><div class="hbar-fill hbar-c4" style="width:{pct}%"></div></div>
						<span class="hbar-val">{count}</span>
					</div>
				{/each}
				{#if Object.keys(errorTypes).length === 0}
					<span class="chart-empty">No errors</span>
				{/if}
			</div>
		{/if}
	</div>

	{#if patternsSorted.length > 0}
		<div class="chart-box">
			<h3>Detected Patterns</h3>
			<div class="hbars">
				{#each showAllPatterns ? patternsSorted : patternsSorted.slice(0, patternLimit) as [label, count]}
					<div class="hbar">
						<span class="hbar-name" style="text-transform:capitalize" title="{label}">{label}</span>
						<div class="hbar-track"><div class="hbar-fill hbar-c3" style="width:{Math.max(8, (count / patternsMax) * 100)}%"></div></div>
						<span class="hbar-val">{count}</span>
					</div>
				{/each}
			</div>
			{#if patternsSorted.length > patternLimit}
				<button class="show-more" onclick={() => showAllPatterns = !showAllPatterns}>
					{showAllPatterns ? 'Show fewer' : `Show all ${patternsSorted.length}`}
				</button>
			{/if}
		</div>
	{/if}

	{#if extra}
		{@render extra()}
	{/if}
</div>

<style>
	.chart-bento { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
	.chart-box { background: white; border-radius: 16px; padding: 22px 24px; }
	.chart-wide { grid-column: span 2; }
	.chart-box h3 { font-size: 13px; font-weight: 700; color: #232326; margin-bottom: 16px; }
	.chart-empty { font-size: 13px; color: #a1a1aa; }

	.hbars { display: flex; flex-direction: column; gap: 8px; }
	.hbar { display: flex; align-items: center; gap: 10px; }
	.hbar-name { width: 100px; font-size: 13px; color: #52525b; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.hbar-track { flex: 1; height: 10px; background: #f4f4f5; border-radius: 5px; overflow: hidden; }
	.hbar-fill { height: 100%; border-radius: 5px; transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
	.hbar-c1 { background: linear-gradient(90deg, #6366f1, #a5b4fc); }
	.hbar-c2 { background: linear-gradient(90deg, #10b981, #6ee7b7); }
	.hbar-c3 { background: linear-gradient(90deg, #8b5cf6, #c4b5fd); }
	.hbar-c4 { background: linear-gradient(90deg, #ef4444, #fca5a5); }
	.hbar-val { width: 40px; font-size: 13px; font-weight: 600; color: #71717a; text-align: right; font-variant-numeric: tabular-nums; }

	.hour-bars { display: flex; align-items: flex-end; gap: 4px; height: 120px; padding-top: 8px; }
	.hour-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
	.hour-fill { width: 100%; border-radius: 4px 4px 0 0; background: linear-gradient(180deg, #8b5cf6, #ddd6fe); transition: height 0.4s; min-height: 2px; }
	.hour-label { font-size: 10px; color: #a1a1aa; margin-top: 4px; }

	.error-details { display: flex; flex-direction: column; gap: 8px; }
	.error-card { background: #fef2f2; border: 1px solid #fecaca; border-radius: 10px; padding: 12px 16px; }
	.error-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
	.error-tool { font-size: 13px; font-weight: 700; color: #991b1b; font-family: 'SF Mono', 'Fira Code', monospace; }
	.error-count { font-size: 11px; font-weight: 600; color: #ef4444; background: #fee2e2; padding: 1px 6px; border-radius: 4px; }
	.error-msg { font-size: 12px; color: #71717a; line-height: 1.5; white-space: pre-wrap; word-break: break-word; max-height: 60px; overflow: hidden; }

	.show-more { display: block; margin: 12px auto 0; font-size: 13px; color: #6366f1; background: none; border: none; cursor: pointer; font-weight: 600; }

	@media (max-width: 768px) {
		.chart-bento { grid-template-columns: 1fr; }
		.chart-wide { grid-column: span 1; }
	}
</style>
