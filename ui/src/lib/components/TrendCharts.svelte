<script lang="ts">
	import type { TrendPoint, TokenDistribution } from '$lib/api';
	import { fmtTokens } from '$lib/format';

	let { trends, tokenDist = null }: { trends: TrendPoint[]; tokenDist?: TokenDistribution | null } = $props();

	const bp = $derived.by(() => {
		if (!tokenDist) return null;
		const logMax = Math.log10(tokenDist.max_val + 1);
		const scale = (v: number) => (Math.log10(v + 1) / logMax) * 100;
		return { ...tokenDist, scale };
	});

	let chartHoverIdx: Record<string, number | null> = $state({});

	const W = 720, H = 180;
	const PAD = { t: 16, r: 16, b: 28, l: 44 };
	const iW = W - PAD.l - PAD.r;
	const iH = H - PAD.t - PAD.b;

	function chartMove(e: MouseEvent, chartId: string) {
		const svg = e.currentTarget as SVGElement;
		const rect = svg.getBoundingClientRect();
		const relX = (e.clientX - rect.left) / rect.width * W;
		const idx = Math.round(((relX - PAD.l) / iW) * (trends.length - 1));
		chartHoverIdx[chartId] = Math.max(0, Math.min(trends.length - 1, idx));
	}

	function chartLeave(chartId: string) { chartHoverIdx[chartId] = null; }
	function xOf(i: number): number { return PAD.l + (i / Math.max(trends.length - 1, 1)) * iW; }

	function linePath(pts: TrendPoint[], key: keyof TrendPoint): string {
		const filtered: { i: number; v: number }[] = [];
		for (let i = 0; i < pts.length; i++) {
			const v = pts[i][key] as number | null;
			if (v != null) filtered.push({ i, v });
		}
		if (filtered.length < 2) return '';
		const maxY = Math.max(...filtered.map(f => f.v), 0.1);
		const minY = Math.min(...filtered.map(f => f.v), 0);
		const range = maxY - minY || 1;
		return filtered.map((f, idx) => {
			const x = xOf(f.i);
			const y = PAD.t + iH - ((f.v - minY) / range) * iH;
			return `${idx === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
		}).join(' ');
	}

	function areaPath(pts: TrendPoint[], key: keyof TrendPoint): string {
		const line = linePath(pts, key);
		if (!line) return '';
		return `${line} L${xOf(pts.length - 1).toFixed(1)},${PAD.t + iH} L${xOf(0).toFixed(1)},${PAD.t + iH} Z`;
	}

	function yScale(pts: TrendPoint[], key: keyof TrendPoint) {
		const vals = pts.map(p => p[key] as number | null).filter(v => v != null) as number[];
		const max = Math.max(...vals, 0.1);
		const min = Math.min(...vals, 0);
		const range = max - min || 1;
		const step = range / 3;
		const ticks = [min, min + step, min + 2 * step, max].map(v => Math.round(v * 10) / 10);
		return { ticks, yOf: (v: number) => PAD.t + iH - ((v - min) / range) * iH };
	}

	function xLabels(pts: TrendPoint[]): { x: number; label: string }[] {
		if (pts.length < 2) return [];
		const step = Math.max(1, Math.floor(pts.length / 6));
		return pts
			.map((p, i) => ({ i, p }))
			.filter(({ i }) => i % step === 0 || i === pts.length - 1)
			.map(({ i, p }) => ({ x: xOf(i), label: p.date.slice(5) }));
	}

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

	const maxBar = $derived(Math.max(...trends.map(t => t.session_count), 1));
	const maxTokBar = $derived(Math.max(...trends.map(t => t.total_tokens), 1));
	const barW = $derived(trends.length > 0 ? Math.max(iW / trends.length - 1, 2) : 2);

	type ChartDef = { id: string; key: keyof TrendPoint; title: string; desc: string; color: string; suffix: string; invertTrend: boolean; type: 'line' | 'bar' };
	const charts: ChartDef[] = [
		{ id: 'c1', key: 'avg_read_edit_ratio', title: 'Read:Edit Ratio', desc: 'Research before modifying. Higher is better.', color: '#3b82f6', suffix: '', invertTrend: false, type: 'line' },
		{ id: 'c2', key: 'avg_error_rate', title: 'Error Rate', desc: 'Failed tool calls %. Lower is better.', color: '#ef4444', suffix: '%', invertTrend: true, type: 'line' },
		{ id: 'c3', key: 'avg_edits_without_read_pct', title: 'Blind Edit Rate', desc: 'Edits without reading first. Lower is better.', color: '#f59e0b', suffix: '%', invertTrend: true, type: 'line' },
		{ id: 'c4', key: 'avg_research_mutation_ratio', title: 'Research:Mutation', desc: 'Read+Grep vs Edit+Write. Higher is better.', color: '#10b981', suffix: '', invertTrend: false, type: 'line' },
		{ id: 'c5', key: 'session_count', title: 'Session Volume', desc: 'Sessions per day.', color: '#8b5cf6', suffix: '', invertTrend: false, type: 'bar' },
		{ id: 'c6', key: 'total_tokens', title: 'Token Usage', desc: 'Tokens consumed per day.', color: '#06b6d4', suffix: '', invertTrend: false, type: 'bar' },
	];

	// Agent distribution from trend data
	const agentDist = $derived.by(() => {
		const counts: Record<string, number> = {};
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
	const totalSessions = $derived(trends.reduce((s, t) => s + t.session_count, 0));
	const totalTokens = $derived(trends.reduce((s, t) => s + t.total_tokens, 0));
</script>

{#if trends.length > 1}
	<div class="charts-grid">
		{#each charts as ch}
			{@const tr = weeklyTrend(trends, ch.key)}
			{@const hi = chartHoverIdx[ch.id] ?? null}
			{@const hPt = hi != null ? trends[hi] : null}
			{@const hVal = hPt ? hPt[ch.key] as number | null : null}
			<div class="chart-card">
				<div class="chart-header">
					<h3>{ch.title}</h3>
					<div class="chart-header-right">
						{#if hPt}
							<span class="chart-hover-val">{hPt.date.slice(5)}: <strong>{hVal != null ? (ch.key === 'total_tokens' ? fmtTokens(hVal) : hVal.toFixed(1)) : '-'}{ch.suffix}</strong></span>
						{/if}
						{#if tr && !hPt}
							<span class="trend-badge" class:up={ch.invertTrend ? tr.dir === 'down' : tr.dir === 'up'} class:down={ch.invertTrend ? tr.dir === 'up' : tr.dir === 'down'}>
								{tr.dir === 'up' ? '↑' : '↓'} {tr.pct}%
							</span>
						{/if}
					</div>
				</div>
				<p class="chart-desc">{ch.desc}</p>
				{#if ch.type === 'line'}
					{@const ys = yScale(trends, ch.key)}
					<svg viewBox="0 0 {W} {H}" class="trend-svg"
						onmousemove={(e) => chartMove(e, ch.id)}
						onmouseleave={() => chartLeave(ch.id)}>
						<defs>
							<linearGradient id="g-{ch.id}" x1="0" y1="0" x2="0" y2="1">
								<stop offset="0%" stop-color={ch.color} stop-opacity="0.12" />
								<stop offset="100%" stop-color={ch.color} stop-opacity="0" />
							</linearGradient>
						</defs>
						{#each ys.ticks as tick}
							<line x1={PAD.l} x2={W - PAD.r} y1={ys.yOf(tick)} y2={ys.yOf(tick)} stroke="#eee" />
							<text x={PAD.l - 6} y={ys.yOf(tick) + 4} text-anchor="end" fill="#b0b0b0" font-size="10">{tick}{ch.suffix}</text>
						{/each}
						<path d={areaPath(trends, ch.key)} fill="url(#g-{ch.id})" />
						<path d={linePath(trends, ch.key)} fill="none" stroke={ch.color} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
						{#if hi != null}
							<line x1={xOf(hi)} x2={xOf(hi)} y1={PAD.t} y2={PAD.t + iH} stroke={ch.color} stroke-width="1" stroke-dasharray="3,3" opacity="0.5" />
							{#if hVal != null}
								<circle cx={xOf(hi)} cy={ys.yOf(hVal)} r="4" fill={ch.color} />
							{/if}
						{/if}
						{#each xLabels(trends) as xl}
							<text x={xl.x} y={H - 4} text-anchor="middle" fill="#b0b0b0" font-size="9">{xl.label}</text>
						{/each}
					</svg>
				{:else}
					{@const maxB = ch.key === 'total_tokens' ? maxTokBar : maxBar}
					{@const barTicks = [0, Math.round(maxB / 3), Math.round(maxB * 2 / 3), maxB]}
					<svg viewBox="0 0 {W} {H}" class="trend-svg"
						onmousemove={(e) => chartMove(e, ch.id)}
						onmouseleave={() => chartLeave(ch.id)}>
						{#each barTicks as tick}
							{@const ty = PAD.t + iH - (tick / maxB) * iH}
							<line x1={PAD.l} x2={W - PAD.r} y1={ty} y2={ty} stroke="#eee" />
							<text x={PAD.l - 6} y={ty + 4} text-anchor="end" fill="#b0b0b0" font-size="10">
								{ch.key === 'total_tokens' ? fmtTokens(tick) : tick}
							</text>
						{/each}
						{#each trends as pt, i}
							{@const v = (pt[ch.key] as number) ?? 0}
							{@const bH = (v / maxB) * iH}
							<rect x={xOf(i) - barW / 2} y={PAD.t + iH - bH} width={barW} height={bH}
								fill={ch.color} opacity={hi === i ? 1 : 0.6} rx="1" />
						{/each}
						{#if hi != null}
							<line x1={xOf(hi)} x2={xOf(hi)} y1={PAD.t} y2={PAD.t + iH} stroke={ch.color} stroke-width="1" stroke-dasharray="3,3" opacity="0.4" />
						{/if}
						{#each xLabels(trends) as xl}
							<text x={xl.x} y={H - 4} text-anchor="middle" fill="#b0b0b0" font-size="9">{xl.label}</text>
						{/each}
					</svg>
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

		{#if bp}
			<div class="chart-card">
				<div class="chart-header">
					<h3>Token Distribution</h3>
					<span class="chart-total">{bp.count} sessions</span>
				</div>
				<p class="chart-desc">Token usage per session. Log scale. Median: {fmtTokens(bp.median)}</p>
				<div class="bp-container">
					<div class="bp-labels">
						<span>Min: {fmtTokens(bp.whisker_low)}</span>
						<span>Q1: {fmtTokens(bp.q1)}</span>
						<span class="bp-median-label">Median: {fmtTokens(bp.median)}</span>
						<span>Q3: {fmtTokens(bp.q3)}</span>
						<span>Max: {fmtTokens(bp.whisker_high)}</span>
					</div>
					<div class="bp-track">
						<div class="bp-whisker" style="left: {bp.scale(bp.whisker_low)}%; width: {bp.scale(bp.q1) - bp.scale(bp.whisker_low)}%"></div>
						<div class="bp-box" style="left: {bp.scale(bp.q1)}%; width: {bp.scale(bp.q3) - bp.scale(bp.q1)}%">
							<div class="bp-median-line" style="left: {((bp.scale(bp.median) - bp.scale(bp.q1)) / Math.max(bp.scale(bp.q3) - bp.scale(bp.q1), 1)) * 100}%"></div>
						</div>
						<div class="bp-whisker" style="left: {bp.scale(bp.q3)}%; width: {bp.scale(bp.whisker_high) - bp.scale(bp.q3)}%"></div>
					</div>
				</div>
			</div>
		{/if}
	</div>
{/if}

<style>
	.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 28px; }
	.chart-card { background: white; border-radius: 16px; padding: 20px 22px; border: 1px solid #e8e5e0; transition: box-shadow 0.25s ease; }
	.chart-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.04); }
	.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1px; }
	.chart-header h3 { font-size: 14px; font-weight: 700; color: #232326; }
	.chart-header-right { display: flex; align-items: center; gap: 6px; }
	.chart-hover-val { font-size: 12px; color: #475569; }
	.chart-desc { font-size: 11px; color: #a1a1aa; margin-bottom: 8px; }
	.chart-total { font-size: 11px; font-weight: 600; color: #8b5cf6; }
	.trend-badge { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 5px; }
	.trend-badge.up { background: #ecfdf5; color: #16a34a; }
	.trend-badge.down { background: #fef2f2; color: #dc2626; }
	.trend-svg { width: 100%; height: auto; cursor: crosshair; }

	.pie-inner { display: flex; align-items: center; gap: 20px; justify-content: center; padding: 8px 0; }
	.pie-svg { width: 120px; height: 120px; flex-shrink: 0; }
	.pie-legend { display: flex; flex-direction: column; gap: 6px; }
	.pie-leg-item { display: flex; align-items: center; gap: 8px; }
	.pie-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
	.pie-leg-name { font-size: 13px; font-weight: 600; color: #232326; font-family: monospace; }
	.pie-leg-val { font-size: 12px; color: #94a3b8; margin-left: auto; }

	.bp-container { padding: 16px 0 4px; }
	.bp-labels { display: flex; justify-content: space-between; font-size: 10px; color: #64748b; margin-bottom: 8px; }
	.bp-median-label { font-weight: 700; color: #232326; }
	.bp-track { position: relative; height: 28px; background: #f1f5f9; border-radius: 4px; }
	.bp-whisker { position: absolute; top: 12px; height: 4px; background: #94a3b8; border-radius: 2px; }
	.bp-box { position: absolute; top: 4px; height: 20px; background: #3b82f6; border-radius: 4px; opacity: 0.7; }
	.bp-median-line { position: absolute; top: 0; width: 2px; height: 100%; background: #1e40af; border-radius: 1px; }

	@media (max-width: 768px) { .charts-grid { grid-template-columns: 1fr; } }
</style>
