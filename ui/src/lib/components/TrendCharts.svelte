<script lang="ts">
	import type { TrendPoint, TokenDistribution } from '$lib/api';
	import type { SessionRead } from '$lib/types';
	import { fmtTokens } from '$lib/format';
	import LineChart from '$lib/components/charts/LineChart.svelte';
	import BarChart from '$lib/components/charts/BarChart.svelte';
	import BoxPlot from '$lib/components/charts/BoxPlot.svelte';

	let { trends, tokenDist = null, sessions = [], sessionCount = 0, projectAgents = undefined }: { trends: TrendPoint[]; tokenDist?: TokenDistribution | null; sessions?: SessionRead[]; sessionCount?: number; projectAgents?: Record<string, number> } = $props();

	function weeklyTrend(pts: TrendPoint[], key: keyof TrendPoint): { dir: string; pct: number } | null {
		const vals = pts.map(p => p[key] as number | null).filter(v => v != null) as number[];
		if (vals.length < 7) return null;
		const r = vals.slice(-7), e = vals.slice(-14, -7);
		if (!e.length) return null;
		const avgR = r.reduce((a, b) => a + b, 0) / r.length;
		const avgE = e.reduce((a, b) => a + b, 0) / e.length;
		if (avgE === 0) return null;
		const pct = Math.round(((avgR - avgE) / avgE) * 100);
		return { dir: pct >= 0 ? 'up' : 'down', pct: Math.abs(pct) };
	}

	type ChartDef = { id: string; key: keyof TrendPoint; title: string; desc: string; color: string; suffix: string; invertTrend: boolean; type: 'line' | 'bar' };
	const charts: ChartDef[] = [
		{ id: 'c1', key: 'avg_read_edit_ratio', title: 'Read:Edit Ratio', desc: 'Research before modifying. Higher is better.', color: '#3b82f6', suffix: '', invertTrend: false, type: 'line' },
		{ id: 'c2', key: 'avg_error_rate', title: 'Error Rate', desc: 'Failed tool calls %. Lower is better.', color: '#ef4444', suffix: '%', invertTrend: true, type: 'line' },
		{ id: 'c3', key: 'avg_edits_without_read_pct', title: 'Blind Edit Rate', desc: 'Edits without reading first. Lower is better.', color: '#f59e0b', suffix: '%', invertTrend: true, type: 'line' },
		{ id: 'c4', key: 'avg_research_mutation_ratio', title: 'Research:Mutation', desc: 'Read+Grep vs Edit+Write. Higher is better.', color: '#10b981', suffix: '', invertTrend: false, type: 'line' },
		{ id: 'c5', key: 'session_count', title: 'Session Volume', desc: 'Sessions per day.', color: '#8b5cf6', suffix: '', invertTrend: false, type: 'bar' },
		{ id: 'c6', key: 'total_tokens', title: 'Token Usage', desc: 'Tokens consumed per day.', color: '#06b6d4', suffix: '', invertTrend: false, type: 'bar' },
	];

	const trendLabels = $derived(trends.map(t => t.date.slice(5)));

	// Agent distribution — prefer API data (full count), then sessions, then trends
	const agentDist = $derived.by(() => {
		const counts: Record<string, number> = {};
		if (projectAgents && Object.keys(projectAgents).length > 0) {
			Object.assign(counts, projectAgents);
		} else if (sessions.length > 0) {
			for (const s of sessions) {
				const agent = s.agent_type || 'unknown';
				counts[agent] = (counts[agent] ?? 0) + 1;
			}
		} else {
			for (const t of trends) {
				if (t.agent_distribution_json) {
					try {
						const dist = JSON.parse(t.agent_distribution_json) as Record<string, number>;
						for (const [agent, count] of Object.entries(dist)) {
							counts[agent] = (counts[agent] ?? 0) + count;
						}
					} catch { /* skip */ }
				}
			}
		}
		const total = Object.values(counts).reduce((s, v) => s + v, 0);
		return Object.entries(counts)
			.map(([name, count]) => ({ name, count, pct: total > 0 ? Math.round(count / total * 100) : 0 }))
			.sort((a, b) => b.count - a.count);
	});
	const agentTotal = $derived(agentDist.reduce((s, a) => s + a.count, 0));
	const pieSlices = $derived.by(() => {
		if (agentTotal === 0) return [];
		let cumAngle = 0;
		return agentDist.map(a => {
			const startAngle = cumAngle;
			const angle = a.count / agentTotal * 360;
			cumAngle += angle;
			const sr = (startAngle - 90) * Math.PI / 180;
			const er = (startAngle + angle - 90) * Math.PI / 180;
			const ac = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#ef4444', '#6366f1'];
			let h = 0;
			for (let i = 0; i < a.name.length; i++) h = ((h << 5) - h + a.name.charCodeAt(i)) | 0;
			return {
				...a, startAngle, angle, large: angle > 180 ? 1 : 0,
				sx: 100 + 80 * Math.cos(sr), sy: 100 + 80 * Math.sin(sr),
				ex: 100 + 80 * Math.cos(er), ey: 100 + 80 * Math.sin(er),
				color: ac[Math.abs(h) % ac.length],
			};
		});
	});
</script>

{#if trends.length > 1}
	<div class="charts-grid">
		{#each charts as ch}
			{@const tr = weeklyTrend(trends, ch.key)}
			<div class="chart-card">
				<div class="chart-header">
					<h3>{ch.title}</h3>
					<div class="chart-header-right">
						{#if tr}
							<span class="trend-badge" class:up={ch.invertTrend ? tr.dir === 'down' : tr.dir === 'up'} class:down={ch.invertTrend ? tr.dir === 'up' : tr.dir === 'down'}>
								{tr.dir === 'up' ? '↑' : '↓'} {tr.pct}%
							</span>
						{/if}
					</div>
				</div>
				<p class="chart-desc">{ch.desc}</p>
				{#if ch.type === 'line'}
					<LineChart
						labels={trendLabels}
						datasets={[{
							label: ch.title,
							data: trends.map(t => (t[ch.key] as number | null) ?? 0),
							color: ch.color,
							fill: true,
						}]}
						height={160}
						yFormat={(v) => ch.key === 'total_tokens' ? fmtTokens(v) : `${v.toFixed(1)}${ch.suffix}`}
						tooltipFormat={(_, i, v) => `${trends[i].date.slice(5)}: ${ch.key === 'total_tokens' ? fmtTokens(v) : `${v.toFixed(1)}${ch.suffix}`}`}
					/>
				{:else}
					<BarChart
						labels={trendLabels}
						data={trends.map(t => (t[ch.key] as number | null) ?? 0)}
						color={ch.color}
						height={160}
						valueFormat={(v) => ch.key === 'total_tokens' ? fmtTokens(v) : String(Math.round(v))}
					/>
				{/if}
			</div>
		{/each}

		{#if pieSlices.length > 0}
			<div class="chart-card">
				<div class="chart-header">
					<h3>Agent Distribution</h3>
					<span class="chart-total">{agentTotal} sessions</span>
				</div>
				<p class="chart-desc">Coding agents used across all sessions.</p>
				<div class="pie-inner">
					<svg viewBox="0 0 200 200" class="pie-svg">
						{#each pieSlices as sl}
							{#if sl.angle >= 359.9}
								<circle cx="100" cy="100" r="80" fill={sl.color} />
							{:else}
								<path d="M100,100 L{sl.sx},{sl.sy} A80,80 0 {sl.large},1 {sl.ex},{sl.ey} Z" fill={sl.color} opacity="0.85" />
							{/if}
						{/each}
						<circle cx="100" cy="100" r="45" fill="white" />
					</svg>
					<div class="pie-legend">
						{#each pieSlices as sl}
							<div class="pie-leg-item">
								<span class="pie-dot" style="background: {sl.color}"></span>
								<span class="pie-leg-name">{sl.name}</span>
								<span class="pie-leg-val">{sl.count} ({sl.pct}%)</span>
							</div>
						{/each}
					</div>
				</div>
			</div>
		{/if}

		{#if tokenDist}
			<div class="chart-card">
				<div class="chart-header">
					<h3>Token Distribution</h3>
					<span class="chart-total">{sessionCount || 0} sessions</span>
				</div>
				<p class="chart-desc">Token usage per session. Median: {fmtTokens(tokenDist.median)}</p>
				<BoxPlot
					whiskerLow={tokenDist.whisker_low}
					q1={tokenDist.q1}
					median={tokenDist.median}
					q3={tokenDist.q3}
					whiskerHigh={tokenDist.whisker_high}
				/>
			</div>
		{/if}
	</div>
{/if}

<style>
	.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 28px; }
	.chart-card {
		background: white;
		border-radius: 16px;
		padding: 22px 24px;
		transition: transform 0.2s ease, box-shadow 0.2s ease;
	}
	.chart-card:hover { transform: translateY(-1px); box-shadow: 0 6px 24px rgba(0,0,0,0.06); }
	.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
	.chart-header h3 { font-size: 13px; font-weight: 700; color: #232326; text-transform: uppercase; letter-spacing: 0.03em; }
	.chart-header-right { display: flex; align-items: center; gap: 6px; }
	.chart-desc { font-size: 11px; color: #a1a1aa; margin-bottom: 10px; }
	.chart-total { font-size: 11px; font-weight: 600; color: #8b5cf6; }
	.trend-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
	.trend-badge.up { background: #ecfdf5; color: #16a34a; }
	.trend-badge.down { background: #fef2f2; color: #dc2626; }

	.pie-inner { display: flex; align-items: center; gap: 20px; justify-content: center; padding: 8px 0; }
	.pie-svg { width: 120px; height: 120px; flex-shrink: 0; }
	.pie-legend { display: flex; flex-direction: column; gap: 6px; }
	.pie-leg-item { display: flex; align-items: center; gap: 8px; }
	.pie-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
	.pie-leg-name { font-size: 13px; font-weight: 600; color: #232326; font-family: monospace; }
	.pie-leg-val { font-size: 12px; color: #94a3b8; margin-left: auto; }

	@media (max-width: 768px) { .charts-grid { grid-template-columns: 1fr; } }
</style>
