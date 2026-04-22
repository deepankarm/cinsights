<script lang="ts">
	import type { TrendPoint, TokenDistribution } from '$lib/api';
	import type { SessionRead } from '$lib/types';
	import { fmtTokens } from '$lib/format';

	let { trends, tokenDist = null, sessions = [], sessionCount = 0 }: { trends: TrendPoint[]; tokenDist?: TokenDistribution | null; sessions?: SessionRead[]; sessionCount?: number } = $props();

	const bp = $derived.by(() => {
		if (!tokenDist) return null;
		const lo = tokenDist.whisker_low;
		const hi = tokenDist.whisker_high;
		const range = hi - lo || 1;
		const scale = (v: number) => ((v - lo) / range) * 100;
		const points = [
			{ label: 'Min', value: tokenDist.whisker_low, x: scale(tokenDist.whisker_low) },
			{ label: 'Q1', value: tokenDist.q1, x: scale(tokenDist.q1) },
			{ label: 'Median', value: tokenDist.median, x: scale(tokenDist.median) },
			{ label: 'Q3', value: tokenDist.q3, x: scale(tokenDist.q3) },
			{ label: 'Max', value: tokenDist.whisker_high, x: scale(tokenDist.whisker_high) },
		];
		return { ...tokenDist, scale, points };
	});

	let bpHover: { label: string; value: number; x: number; y: number } | null = $state(null);

	function bpMove(e: MouseEvent) {
		if (!bp) return;
		const svg = e.currentTarget as SVGElement;
		const rect = svg.getBoundingClientRect();
		const relX = (e.clientX - rect.left) / rect.width * 100;
		// Find closest point
		let closest = bp.points[0];
		let minDist = Infinity;
		for (const p of bp.points) {
			const d = Math.abs(p.x - relX);
			if (d < minDist) { minDist = d; closest = p; }
		}
		bpHover = { ...closest, y: e.clientY - rect.top };
	}

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

	// Agent distribution — prefer sessions (accurate), fall back to trend data (pre-aggregated)
	const agentDist = $derived.by(() => {
		const counts: Record<string, number> = {};
		if (sessions.length > 0) {
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
								<stop offset="0%" stop-color={ch.color} stop-opacity="0.25" />
								<stop offset="100%" stop-color={ch.color} stop-opacity="0.03" />
							</linearGradient>
						</defs>
						{#each ys.ticks as tick}
							<line x1={PAD.l} x2={W - PAD.r} y1={ys.yOf(tick)} y2={ys.yOf(tick)} stroke="#f0f0f0" stroke-dasharray="4,4" />
							<text x={PAD.l - 6} y={ys.yOf(tick) + 4} text-anchor="end" fill="#b0b0b0" font-size="10">{tick}{ch.suffix}</text>
						{/each}
						<path d={areaPath(trends, ch.key)} fill="url(#g-{ch.id})" />
						<path d={linePath(trends, ch.key)} fill="none" stroke={ch.color} stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
						{#if hi != null}
							<line x1={xOf(hi)} x2={xOf(hi)} y1={PAD.t} y2={PAD.t + iH} stroke={ch.color} stroke-width="1" stroke-dasharray="4,4" opacity="0.3" />
							{#if hVal != null}
								<circle cx={xOf(hi)} cy={ys.yOf(hVal)} r="5" fill="white" stroke={ch.color} stroke-width="2.5" />
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
							<line x1={PAD.l} x2={W - PAD.r} y1={ty} y2={ty} stroke="#f0f0f0" stroke-dasharray="4,4" />
							<text x={PAD.l - 6} y={ty + 4} text-anchor="end" fill="#b0b0b0" font-size="10">
								{ch.key === 'total_tokens' ? fmtTokens(tick) : tick}
							</text>
						{/each}
						<defs>
							<linearGradient id="bg-{ch.id}" x1="0" y1="0" x2="0" y2="1">
								<stop offset="0%" stop-color={ch.color} stop-opacity="0.9" />
								<stop offset="100%" stop-color={ch.color} stop-opacity="0.5" />
							</linearGradient>
						</defs>
						{#each trends as pt, i}
							{@const v = (pt[ch.key] as number) ?? 0}
							{@const bH = (v / maxB) * iH}
							<rect x={xOf(i) - barW / 2} y={PAD.t + iH - bH} width={barW} height={bH}
								fill="url(#bg-{ch.id})" opacity={hi === i ? 1 : 0.7} rx="3" />
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
			{@const PAD_X = 40}
			{@const BW = 720}
			{@const BH = 90}
			{@const iw = BW - PAD_X * 2}
			{@const cy = 50}
			{@const boxH = 28}
			{@const x = (v: number) => PAD_X + (bp.scale(v) / 100) * iw}
			<div class="chart-card">
				<div class="chart-header">
					<h3>Token Distribution</h3>
					<span class="chart-total">{sessionCount || bp.count} sessions</span>
				</div>
				<p class="chart-desc">Token usage per session. Median: {fmtTokens(bp.median)}</p>
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<svg class="bp-svg" viewBox="0 0 {BW} {BH}"
					onmousemove={bpMove} onmouseleave={() => bpHover = null}>
					<!-- whiskers -->
					<line x1={x(bp.whisker_low)} x2={x(bp.q1)} y1={cy} y2={cy} stroke="#94a3b8" stroke-width="2" />
					<line x1={x(bp.q3)} x2={x(bp.whisker_high)} y1={cy} y2={cy} stroke="#94a3b8" stroke-width="2" />
					<!-- whisker caps -->
					<line x1={x(bp.whisker_low)} x2={x(bp.whisker_low)} y1={cy - 8} y2={cy + 8} stroke="#94a3b8" stroke-width="2" />
					<line x1={x(bp.whisker_high)} x2={x(bp.whisker_high)} y1={cy - 8} y2={cy + 8} stroke="#94a3b8" stroke-width="2" />
					<!-- box (Q1–Q3) -->
					<rect x={x(bp.q1)} y={cy - boxH / 2} width={x(bp.q3) - x(bp.q1)} height={boxH}
						rx="4" fill="url(#bpGrad)" stroke="#3b82f6" stroke-width="1" />
					<!-- median line -->
					<line x1={x(bp.median)} x2={x(bp.median)} y1={cy - boxH / 2} y2={cy + boxH / 2}
						stroke="#1e3a5f" stroke-width="2.5" />
					<!-- labels -->
					<text x={x(bp.whisker_low)} y={cy + boxH / 2 + 14} text-anchor="start" class="bp-tick">{fmtTokens(bp.whisker_low)}</text>
					<text x={x(bp.q1)} y={cy - boxH / 2 - 6} text-anchor="middle" class="bp-tick">{fmtTokens(bp.q1)}</text>
					<text x={x(bp.median)} y={cy - boxH / 2 - 6} text-anchor="middle" class="bp-tick bp-tick-median">{fmtTokens(bp.median)}</text>
					<text x={x(bp.q3)} y={cy + boxH / 2 + 14} text-anchor="middle" class="bp-tick">{fmtTokens(bp.q3)}</text>
					<text x={x(bp.whisker_high)} y={cy + boxH / 2 + 14} text-anchor="end" class="bp-tick">{fmtTokens(bp.whisker_high)}</text>
					<!-- hover highlight -->
					{#if bpHover}
						<circle cx={x(bpHover.value)} cy={cy} r="5" fill="#8b5cf6" />
						<rect x={x(bpHover.value) - 45} y={cy - boxH / 2 - 28} width="90" height="20" rx="4" fill="#1e293b" />
						<text x={x(bpHover.value)} y={cy - boxH / 2 - 14} text-anchor="middle" fill="white" font-size="11" font-weight="600">{bpHover.label}: {fmtTokens(bpHover.value)}</text>
					{/if}
					<defs>
						<linearGradient id="bpGrad" x1="0%" x2="100%">
							<stop offset="0%" stop-color="#3b82f6" />
							<stop offset="100%" stop-color="#93c5fd" />
						</linearGradient>
					</defs>
				</svg>
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
	.chart-hover-val { font-size: 12px; color: #475569; font-weight: 600; font-variant-numeric: tabular-nums; }
	.chart-desc { font-size: 11px; color: #a1a1aa; margin-bottom: 10px; }
	.chart-total { font-size: 11px; font-weight: 600; color: #8b5cf6; }
	.trend-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
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

	.bp-svg { width: 100%; height: auto; cursor: crosshair; margin-top: 8px; }
	.bp-tick { font-size: 10px; fill: #64748b; }
	.bp-tick-median { font-weight: 700; fill: #232326; }

	@media (max-width: 768px) { .charts-grid { grid-template-columns: 1fr; } }
</style>
