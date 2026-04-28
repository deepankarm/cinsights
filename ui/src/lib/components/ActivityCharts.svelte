<script lang="ts">
	import type { Snippet } from 'svelte';
	import { barPct, maxVal } from '$lib/format';
	import BarChart from '$lib/components/charts/BarChart.svelte';

	export interface ErrorDetail {
		tool: string;
		message: string;
		count: number;
	}


	let {
		toolDistribution = {},
		languageDistribution = {},
		timeOfDay = {},
		errorTypes = {},
		errorDetails = undefined,
		insightLabels = undefined,
		labelCategories = undefined,
		labelTrends = undefined,
		analyzedCount = undefined,
		sessionCount = undefined,
		scopeUser = undefined,
		scopeProject = undefined,
		extra = undefined,
	}: {
		toolDistribution?: Record<string, number>;
		languageDistribution?: Record<string, number>;
		timeOfDay?: Record<string, number>;
		errorTypes?: Record<string, number>;
		errorDetails?: ErrorDetail[];
		insightLabels?: Record<string, number> | null;
		labelCategories?: Record<string, string> | null;
		labelTrends?: Array<{ date: string; labels: Record<string, number> }> | null;
		analyzedCount?: number;
		sessionCount?: number;
		scopeUser?: string;
		scopeProject?: string;
		extra?: Snippet;
	} = $props();

	function patternLink(label: string): string {
		let url = `/sessions?label=${encodeURIComponent(label)}&cat=${labelCategories?.[label] ?? ''}`;
		if (scopeUser) url += `&user=${encodeURIComponent(scopeUser)}`;
		if (scopeProject) url += `&project=${encodeURIComponent(scopeProject)}`;
		return url;
	}

	const CAT_COLORS: Record<string, string> = {
		friction: '#ef4444',
		win: '#10b981',
		recommendation: '#3b82f6',
		pattern: '#8b5cf6',
		skill_proposal: '#f59e0b',
		summary: '#6b7280',
	};
	function catColor(label: string): string {
		const cat = labelCategories?.[label] ?? 'pattern';
		return CAT_COLORS[cat] ?? '#8b5cf6';
	}
	const ACTIONABLE_CATS = new Set(['friction', 'win', 'recommendation']);
	function catIcon(label: string): string {
		const cat = labelCategories?.[label] ?? 'pattern';
		return cat === 'friction' ? '▼' : cat === 'win' ? '▲' : cat === 'recommendation' ? '💡' : '·';
	}

	let patternsSorted = $derived(
		Object.entries(insightLabels ?? {})
			.sort((a, b) => b[1] - a[1])
			.filter(([lbl, c]) => c >= ((analyzedCount ?? 0) <= 5 ? 1 : 2) && ACTIONABLE_CATS.has(labelCategories?.[lbl] ?? ''))
	);
	const defaultPatternLimit = 10;
</script>

<div class="chart-bento">
	<div class="chart-box">
		<h3>Tools</h3>
		{#if Object.keys(toolDistribution).length > 0}
			{@const entries = Object.entries(toolDistribution).slice(0, 8)}
			<BarChart
				labels={entries.map(([n]) => n)}
				data={entries.map(([, c]) => c)}
				color="#6366f1"
				horizontal={true}
				height={Math.max(entries.length * 28, 120)}
			/>
		{:else}
			<span class="chart-empty">No data</span>
		{/if}
	</div>
	<div class="chart-box">
		<h3>Languages</h3>
		{#if Object.keys(languageDistribution).length > 0}
			{@const entries = Object.entries(languageDistribution).slice(0, 6)}
			<BarChart
				labels={entries.map(([n]) => n)}
				data={entries.map(([, c]) => c)}
				color="#10b981"
				horizontal={true}
				height={Math.max(entries.length * 28, 120)}
			/>
		{:else}
			<span class="chart-empty">No data</span>
		{/if}
	</div>
	<div class="chart-box">
		<h3>Coding hours <span style="font-weight:400;color:#94a3b8;font-size:11px">(UTC)</span></h3>
		<BarChart
			labels={Array.from({length: 24}, (_, i) => String(i))}
			data={Array.from({length: 24}, (_, i) => timeOfDay[String(i)] ?? 0)}
			color="#8b5cf6"
			horizontal={false}
			height={140}
		/>
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
		{:else if Object.keys(errorTypes).length > 0}
			{@const entries = Object.entries(errorTypes).slice(0, 5)}
			<BarChart
				labels={entries.map(([n]) => n)}
				data={entries.map(([, c]) => c)}
				color="#ef4444"
				horizontal={true}
				height={Math.max(entries.length * 28, 120)}
			/>
		{:else}
			<span class="chart-empty">No errors</span>
		{/if}
	</div>

	{#if patternsSorted.length > 0}
		{@const allPatterns = patternsSorted}
		{@const visiblePatterns = allPatterns.slice(0, defaultPatternLimit)}
		{@const visibleLabels = visiblePatterns.map(([l]) => l)}
		{@const hasTrends = labelTrends && labelTrends.length > 1}
		{@const maxDotVal = hasTrends ? Math.max(...labelTrends!.flatMap(d => Object.values(d.labels)), 1) : 1}
		<div class="chart-box chart-wide">
			<div class="pattern-header">
				<h3>Behavioral Patterns</h3>
				<div class="pattern-meta">
					<div class="pattern-legend">
						<span class="pattern-legend-item" style="color:#ef4444">▼ friction</span>
						<span class="pattern-legend-item" style="color:#10b981">▲ win</span>
						<span class="pattern-legend-item" style="color:#3b82f6">💡 recommendation</span>
					</div>
					{#if analyzedCount && sessionCount}
						<div class="pattern-coverage">Based on {analyzedCount} of {sessionCount} sessions</div>
					{/if}
				</div>
			</div>
			<div class="dot-wrap">
				<div class="dot-labels">
					{#if hasTrends}<div class="dot-date-corner"></div>{/if}
					{#each visiblePatterns as [label, count]}
						<a class="dot-label-row" href="{patternLink(label)}" title="View sessions with this pattern">
							<span class="dot-cat-icon" style="color:{catColor(label)}" title="{labelCategories?.[label] ?? 'pattern'}">{catIcon(label)}</span>
							<span class="dot-label" title="{label}">{(label.charAt(0).toUpperCase() + label.slice(1)).replace(/claude\.md/gi, 'CLAUDE.md')}</span>
							<span class="dot-count" style="color:{catColor(label)}">{count}</span>
						</a>
					{/each}
					</div>
				{#if hasTrends}
					<div class="dot-scroll">
						<div class="dot-grid" style="grid-template-columns: repeat({labelTrends!.length}, 36px)">
							{#each labelTrends! as day}
								<div class="dot-date">{day.date.slice(5)}</div>
							{/each}
							{#each visibleLabels as label}
								{#each labelTrends! as day}
									{@const val = day.labels[label] ?? 0}
									<div class="dot-cell">
										{#if val > 0}
											{@const size = 8 + Math.min(val / maxDotVal, 1) * 16}
											<div class="dot-circle" style="background:{catColor(label)}; width:{size}px; height:{size}px" title="{label}: {val} on {day.date}"></div>
										{/if}
									</div>
								{/each}
							{/each}
						</div>
					</div>
				{/if}
			</div>
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

	.error-details { display: flex; flex-direction: column; gap: 8px; }
	.error-card { background: #fef2f2; border: 1px solid #fecaca; border-radius: 10px; padding: 12px 16px; }
	.error-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
	.error-tool { font-size: 13px; font-weight: 700; color: #991b1b; font-family: 'SF Mono', 'Fira Code', monospace; }
	.error-count { font-size: 11px; font-weight: 600; color: #ef4444; background: #fee2e2; padding: 1px 6px; border-radius: 4px; }
	.error-msg { font-size: 12px; color: #71717a; line-height: 1.5; white-space: pre-wrap; word-break: break-word; max-height: 60px; overflow: hidden; }

	.show-more { display: block; margin: 12px auto 0; font-size: 13px; color: #6366f1; background: none; border: none; cursor: pointer; font-weight: 600; }

	/* Pattern header + legend */
	.pattern-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
	.pattern-header h3 { margin-bottom: 0; }
	.pattern-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
	.pattern-legend { display: flex; gap: 12px; }
	.pattern-legend-item { font-size: 11px; font-weight: 600; }
	.pattern-coverage { font-size: 11px; color: #a1a1aa; }

	/* Combined patterns + trends */
	.dot-wrap { display: flex; gap: 0; overflow: hidden; }
	.dot-labels { flex-shrink: 0; width: fit-content; max-width: 320px; }
	.dot-date-corner { height: 28px; }
	.dot-label-row { display: flex; align-items: center; gap: 6px; height: 32px; padding-right: 12px; text-decoration: none; border-radius: 6px; cursor: pointer; }
	.dot-label-row:hover { background: #f8f8fa; }
	.dot-cat-icon { font-size: 10px; flex-shrink: 0; width: 12px; text-align: center; }
	.dot-label { font-size: 12px; color: #52525b; white-space: nowrap; }
	.dot-count { font-size: 12px; font-weight: 700; flex-shrink: 0; font-variant-numeric: tabular-nums; }
	.dot-scroll { flex: 1; overflow-x: auto; overflow-y: hidden; }
	.dot-grid { display: grid; gap: 0; align-items: center; }
	.dot-date { font-size: 10px; color: #a1a1aa; text-align: center; height: 28px; line-height: 28px; transform: rotate(-45deg); transform-origin: center; }
	.dot-cell { display: flex; align-items: center; justify-content: center; height: 32px; }
	.dot-circle { border-radius: 50%; opacity: 0.75; transition: transform 0.15s; cursor: default; }
	.dot-circle:hover { transform: scale(1.4); opacity: 1; }

	@media (max-width: 768px) {
		.chart-bento { grid-template-columns: 1fr; }
		.chart-wide { grid-column: span 1; }
	}
</style>
