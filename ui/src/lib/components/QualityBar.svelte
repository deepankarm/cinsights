<script lang="ts">
	import type { QualityMetric } from '$lib/format';

	let { metrics }: { metrics: QualityMetric[] } = $props();
	let hoveredMetric: string | null = $state(null);

	const metricDescs: Record<string, string> = {
		'Read:Edit': 'Files read per file edited. Higher = more research before changes. Good: 5+, Concerning: <2',
		'Blind edits': '% of edits where the file was never read first. Lower is better. Good: <10%, Bad: >30%',
		'Research:Mut': 'Research ops (Read+Grep+Glob) per mutation (Edit+Write). Higher = more thorough.',
		'Error rate': '% of tool calls that failed. Includes permission denials and tool errors.',
		'Write vs Edit': 'Full-file rewrites as % of all code mutations. High = agent rewrites instead of patching.',
		'Thrashing': 'Avg consecutive edits to the same file. High = agent struggling with a file.',
		'Subagents': '% of tool calls that spawn sub-agents (Agent/Task tools).',
		'Ctx pressure': 'How fast context fills up (0-1). High = approaching context window limits.',
		'Tools/turn': 'Tool calls per conversation turn. Higher = more autonomous per prompt.',
		'Avg duration': 'Average wall-clock time per session.',
	};
</script>

<div class="quality-bar">
	{#each metrics as m}
		<div class="qb-item"
			onmouseenter={() => hoveredMetric = m.label}
			onmouseleave={() => hoveredMetric = null}>
			<span class="qb-val">{m.value}</span>
			<span class="qb-label">{m.label}</span>
			{#if m.teamAvg}
				<span class="qb-avg" style={m.deltaColor ? `color: ${m.deltaColor}` : ''}>{m.deltaColor ? (m.deltaAbove ? '▲' : '▼') : ''} avg {m.teamAvg}</span>
			{/if}
		</div>
	{/each}
</div>
{#if hoveredMetric && metricDescs[hoveredMetric]}
	<div class="metric-tooltip">
		<strong>{hoveredMetric}</strong>: {metricDescs[hoveredMetric]}
	</div>
{/if}

<style>
	.quality-bar {
		display: flex; flex-wrap: wrap; gap: 0; margin-bottom: 4px;
		background: white; border: 1px solid #e8e5e0; border-radius: 16px; overflow: hidden;
	}
	.qb-item { text-align: center; flex: 1; min-width: 80px; padding: 12px 8px; border-right: 1px solid #f1f5f9; cursor: help; transition: background 0.15s; }
	.qb-item:last-child { border-right: none; }
	.qb-item:hover { background: #f0f4ff; }
	.qb-val { display: block; font-size: 16px; font-weight: 700; color: #232326; }
	.qb-label { display: block; font-size: 9px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }
	.qb-avg { display: block; font-size: 9px; color: #c4c4cc; margin-top: 1px; }

	.metric-tooltip {
		background: #1e293b; color: #e2e8f0; font-size: 12px; padding: 8px 12px; border-radius: 6px;
		margin-bottom: 16px; line-height: 1.5;
	}
	.metric-tooltip strong { color: white; }
</style>
