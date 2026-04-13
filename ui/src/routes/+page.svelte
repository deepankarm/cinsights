<script lang="ts">
	import { onMount } from 'svelte';
	import { getStats, getTrends, getUsers, getProjects, type TrendPoint, type UserSummary, type ProjectRead } from '$lib/api';
	import type { StatsResponse } from '$lib/types';

	let stats: StatsResponse | null = $state(null);
	let trends: TrendPoint[] = $state([]);
	let users: UserSummary[] = $state([]);
	let projects: ProjectRead[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);
	let hoveredUser: UserSummary | null = $state(null);
	let hoverPos = $state({ x: 0, y: 0 });

	// Per-chart hover state
	let chartHoverIdx: Record<string, number | null> = $state({});

	onMount(async () => {
		try {
			[stats, trends, users, projects] = await Promise.all([
				getStats(), getTrends(), getUsers(), getProjects(),
			]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load dashboard';
		} finally {
			loading = false;
		}
	});

	const W = 720, H = 180;
	const PAD = { t: 16, r: 16, b: 28, l: 44 };
	const iW = W - PAD.l - PAD.r;
	const iH = H - PAD.t - PAD.b;

	function chartMove(e: MouseEvent, chartId: string) {
		const svg = (e.currentTarget as SVGElement);
		const rect = svg.getBoundingClientRect();
		const relX = (e.clientX - rect.left) / rect.width * W;
		const idx = Math.round(((relX - PAD.l) / iW) * (trends.length - 1));
		chartHoverIdx[chartId] = Math.max(0, Math.min(trends.length - 1, idx));
	}

	function chartLeave(chartId: string) {
		chartHoverIdx[chartId] = null;
	}

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
		return `${line} L${xOf(pts.length - 1).toFixed(1)},${(PAD.t + iH)} L${xOf(0).toFixed(1)},${(PAD.t + iH)} Z`;
	}

	function yScale(pts: TrendPoint[], key: keyof TrendPoint) {
		const vals = pts.map(p => p[key] as number | null).filter(v => v != null) as number[];
		const max = Math.max(...vals, 0.1);
		const min = Math.min(...vals, 0);
		const range = max - min || 1;
		const step = range / 3;
		const ticks = [min, min + step, min + 2 * step, max].map(v => Math.round(v * 10) / 10);
		return { min, max, range, ticks, yOf: (v: number) => PAD.t + iH - ((v - min) / range) * iH };
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

	function fmtDur(ms: number | null): string {
		if (!ms) return '-';
		const mins = Math.floor(ms / 60000);
		if (mins >= 60) return `${(mins / 60).toFixed(1)}h`;
		return `${mins}m`;
	}
	function fmtTokens(n: number): string {
		if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
		if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
		if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
		return n.toString();
	}
	function fmtNum(v: number | null, suffix = ''): string {
		if (v == null) return '-';
		return v.toFixed(1) + suffix;
	}

	const avatarColors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#ef4444', '#6366f1'];
	function avatarColor(name: string): string {
		let h = 0;
		for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
		return avatarColors[Math.abs(h) % avatarColors.length];
	}

	const avgRE = $derived.by(() => {
		const v = trends.filter(t => t.avg_read_edit_ratio != null);
		return v.length ? v.reduce((s, t) => s + (t.avg_read_edit_ratio ?? 0), 0) / v.length : 0;
	});
	const daysTracked = $derived(new Set(trends.map(t => t.date)).size);
	const latestDate = $derived(trends.length ? trends[trends.length - 1].date : '-');
	const totalSessions = $derived(trends.reduce((s, t) => s + t.session_count, 0));
	const totalTokens = $derived(trends.reduce((s, t) => s + t.total_tokens, 0));
	const agentTotal = $derived(agentDist.reduce((s, a) => s + a.count, 0));

	// Pre-compute pie chart slices
	const pieSlices = $derived.by(() => {
		if (agentTotal === 0) return [];
		let cumAngle = 0;
		return agentDist.map(a => {
			const startAngle = cumAngle;
			const angle = a.count / agentTotal * 360;
			cumAngle += angle;
			const large = angle > 180 ? 1 : 0;
			const sr = (startAngle - 90) * Math.PI / 180;
			const er = (startAngle + angle - 90) * Math.PI / 180;
			return {
				...a,
				startAngle, angle, large,
				sx: 100 + 80 * Math.cos(sr), sy: 100 + 80 * Math.sin(sr),
				ex: 100 + 80 * Math.cos(er), ey: 100 + 80 * Math.sin(er),
				color: avatarColor(a.name),
			};
		});
	});

	const agentDist = $derived.by(() => {
		const counts: Record<string, number> = {};
		for (const u of users) {
			// Each user has agents list but not per-agent session counts
			// Use session_count distributed equally as approximation
			// Better: get from API. For now, use agent list presence.
		}
		// Actually count from the user summaries — each user's agents
		// We need per-agent session counts. Let's compute from trends agent_distribution_json
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

	type ChartDef = { id: string; key: keyof TrendPoint; title: string; desc: string; color: string; suffix: string; invertTrend: boolean; type: 'line' | 'bar' };
	const charts: ChartDef[] = [
		{ id: 'c1', key: 'avg_read_edit_ratio', title: 'Read:Edit Ratio', desc: 'Research before modifying. Higher is better.', color: '#3b82f6', suffix: '', invertTrend: false, type: 'line' },
		{ id: 'c2', key: 'avg_error_rate', title: 'Error Rate', desc: 'Failed tool calls %. Lower is better.', color: '#ef4444', suffix: '%', invertTrend: true, type: 'line' },
		{ id: 'c3', key: 'avg_edits_without_read_pct', title: 'Blind Edit Rate', desc: 'Edits without reading first. Lower is better.', color: '#f59e0b', suffix: '%', invertTrend: true, type: 'line' },
		{ id: 'c4', key: 'avg_research_mutation_ratio', title: 'Research:Mutation', desc: 'Read+Grep vs Edit+Write. Higher is better.', color: '#10b981', suffix: '', invertTrend: false, type: 'line' },
		{ id: 'c5', key: 'session_count', title: 'Session Volume', desc: 'Sessions per day.', color: '#8b5cf6', suffix: '', invertTrend: false, type: 'bar' },
		{ id: 'c6', key: 'total_tokens', title: 'Token Usage', desc: 'Tokens consumed per day.', color: '#06b6d4', suffix: '', invertTrend: false, type: 'bar' },
	];
</script>

<svelte:head><title>cinsights</title></svelte:head>

{#if loading}
	<div class="loading">Loading dashboard...</div>
{:else if error}
	<div class="loading" style="color: #dc2626">{error}</div>
{:else}
	<div class="hero">
		<div class="hero-metric">
			<div class="hero-value">{stats?.total_sessions ?? 0}</div>
			<div class="hero-label">Sessions</div>
			<div class="hero-sub">{stats?.analyzed_sessions ?? 0} analyzed &middot; {(stats?.total_sessions ?? 0) - (stats?.analyzed_sessions ?? 0)} indexed</div>
		</div>
		<div class="hero-metric">
			<div class="hero-value">{fmtTokens(totalTokens)}</div>
			<div class="hero-label">Total Tokens</div>
			<div class="hero-sub">across all sessions</div>
		</div>
		<div class="hero-metric">
			<div class="hero-value">{users.length}</div>
			<div class="hero-label">Developers</div>
			<div class="hero-sub">{projects.length} projects</div>
		</div>
		<div class="hero-metric">
			<div class="hero-value">{daysTracked}</div>
			<div class="hero-label">Days tracked</div>
			<div class="hero-sub">{latestDate.slice(5)} latest</div>
		</div>
	</div>

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
						{@const maxB = Math.max(...trends.map(t => (t[ch.key] as number) ?? 0), 1)}
						{@const bW = Math.max(iW / trends.length - 1, 2)}
						<svg viewBox="0 0 {W} {H}" class="trend-svg"
							onmousemove={(e) => chartMove(e, ch.id)}
							onmouseleave={() => chartLeave(ch.id)}>
							{#each trends as pt, i}
								{@const v = (pt[ch.key] as number) ?? 0}
								{@const bH = (v / maxB) * iH}
								<rect x={xOf(i) - bW / 2} y={PAD.t + iH - bH} width={bW} height={bH}
									fill={hi === i ? ch.color : ch.color} opacity={hi === i ? 1 : 0.6} rx="1" />
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

			<!-- Agent Distribution pie -->
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
		</div>
	{/if}

	{#if users.length > 0}
		<div class="section">
			<h2>Developers</h2>
			<p class="section-desc">{users.length} developers across {projects.length} projects. Hover for details.</p>
			<div class="users-grid">
				{#each users as u}
					<a href="/sessions?user={encodeURIComponent(u.user_id)}" class="user-card"
						onmouseenter={(e) => { hoveredUser = u; hoverPos = { x: e.clientX, y: e.clientY }; }}
						onmousemove={(e) => { hoverPos = { x: e.clientX, y: e.clientY }; }}
						onmouseleave={() => { hoveredUser = null; }}>
						<div class="user-header">
							<span class="avatar" style="background: {avatarColor(u.display_name)}">{u.display_name[0].toUpperCase()}</span>
							<div class="user-info">
								<div class="user-name">{u.display_name}</div>
								<div class="user-meta">{u.session_count} sessions &middot; {u.agents.join(', ')}</div>
							</div>
						</div>
						<div class="user-metrics">
							<div class="um"><span class="um-val">{fmtNum(u.avg_read_edit_ratio)}</span><span class="um-label">R:E</span></div>
							<div class="um"><span class="um-val">{fmtNum(u.avg_error_rate, '%')}</span><span class="um-label">Errors</span></div>
							<div class="um"><span class="um-val">{fmtNum(u.avg_turn_count)}</span><span class="um-label">Turns/s</span></div>
							<div class="um"><span class="um-val">{fmtDur(u.avg_duration_ms)}</span><span class="um-label">Avg dur</span></div>
						</div>
					</a>
				{/each}
			</div>
		</div>

		{#if hoveredUser}
			{@const u = hoveredUser}
			{@const panelW = 380}
			{@const panelH = 340}
			{@const px = Math.min(hoverPos.x + 16, window.innerWidth - panelW - 20)}
			{@const py = Math.min(hoverPos.y - panelH / 2, window.innerHeight - panelH - 20)}
			<div class="hover-panel" style="left: {Math.max(8, px)}px; top: {Math.max(8, py)}px">
				<div class="hp-header">
					<span class="avatar" style="background: {avatarColor(u.display_name)}">{u.display_name[0].toUpperCase()}</span>
					<div>
						<div class="hp-name">{u.display_name}</div>
						<div class="hp-email">{u.user_id}</div>
					</div>
				</div>
				<div class="hp-tags">
					{#each u.projects as p}
						<span class="hp-tag project">{p}</span>
					{/each}
					{#each u.agents as a}
						<span class="hp-tag agent">{a}</span>
					{/each}
					{#each u.sources as s}
						<span class="hp-tag source">{s}</span>
					{/each}
				</div>
				<div class="hp-grid">
					<div class="hp-item"><span class="hp-val">{u.session_count}</span><span class="hp-label">Sessions</span></div>
					<div class="hp-item"><span class="hp-val">{u.analyzed_count}</span><span class="hp-label">Analyzed</span></div>
					<div class="hp-item"><span class="hp-val">{fmtTokens(u.total_tokens)}</span><span class="hp-label">Tokens</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_read_edit_ratio)}</span><span class="hp-label">Read:Edit</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_edits_without_read_pct, '%')}</span><span class="hp-label">Blind edits</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_research_mutation_ratio)}</span><span class="hp-label">Research:Mut</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_write_vs_edit_pct, '%')}</span><span class="hp-label">Write vs Edit</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_error_rate, '%')}</span><span class="hp-label">Error rate</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_repeated_edits)}</span><span class="hp-label">Thrashing</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_subagent_spawn_rate, '%')}</span><span class="hp-label">Subagents</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_context_pressure)}</span><span class="hp-label">Ctx pressure</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_tool_calls_per_turn)}</span><span class="hp-label">Tools/turn</span></div>
					<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_turn_count)}</span><span class="hp-label">Turns/sess</span></div>
					<div class="hp-item"><span class="hp-val">{fmtDur(u.avg_duration_ms)}</span><span class="hp-label">Avg duration</span></div>
				</div>
			</div>
		{/if}
	{/if}

	{#if projects.length > 0}
		<div class="section">
			<h2>Projects</h2>
			<div class="project-cards">
				{#each projects as p}
					<a href="/report?project={encodeURIComponent(p.name)}" class="project-link">
						<div class="project-mini">
							<div class="pm-name">{p.name}</div>
							<div class="pm-stats">
								<span>{p.session_count} sessions</span>
								<span>{p.total_tool_calls.toLocaleString()} tools</span>
							</div>
							{#if p.has_digest}<span class="pm-badge">Report ready</span>{/if}
						</div>
					</a>
				{/each}
			</div>
		</div>
	{/if}
{/if}

<style>
	.loading { text-align: center; padding: 80px; color: #94a3b8; }

	.hero { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }
	.hero-metric { background: white; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #e8e5e0; }
	.hero-value { font-size: 36px; font-weight: 800; letter-spacing: -2px; color: #232326; line-height: 1; }
	.hero-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #70707a; margin-top: 6px; }
	.hero-sub { font-size: 11px; color: #a1a1aa; margin-top: 2px; }

	.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 28px; }
	.chart-card { background: white; border-radius: 12px; padding: 16px; border: 1px solid #e8e5e0; }
	.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1px; }
	.chart-header h3 { font-size: 14px; font-weight: 700; color: #232326; }
	.chart-header-right { display: flex; align-items: center; gap: 6px; }
	.chart-hover-val { font-size: 12px; color: #475569; }
	.chart-desc { font-size: 11px; color: #a1a1aa; margin-bottom: 8px; }
	.trend-badge { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 5px; }
	.trend-badge.up { background: #ecfdf5; color: #16a34a; }
	.trend-badge.down { background: #fef2f2; color: #dc2626; }
	.trend-svg { width: 100%; height: auto; cursor: crosshair; }

	.section { margin-bottom: 28px; }
	h2 { font-size: 17px; font-weight: 700; color: #232326; margin-bottom: 2px; }
	.section-desc { font-size: 12px; color: #a1a1aa; margin-bottom: 14px; }

	.users-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
	.user-card { background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 14px; text-decoration: none; transition: border-color 0.15s, box-shadow 0.15s; cursor: pointer; }
	.user-card:hover { border-color: #3b82f6; box-shadow: 0 2px 8px rgba(59,130,246,0.08); }
	.user-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
	.avatar { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 15px; flex-shrink: 0; }
	.user-name { font-size: 14px; font-weight: 600; color: #232326; }
	.user-meta { font-size: 11px; color: #a1a1aa; }
	.user-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
	.um { text-align: center; }
	.um-val { display: block; font-size: 15px; font-weight: 700; color: #232326; }
	.um-label { display: block; font-size: 9px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }

	.hover-panel { position: fixed; width: 380px; background: white; border: 1px solid #d4d4d8; border-radius: 14px; padding: 16px; box-shadow: 0 12px 40px rgba(0,0,0,0.15); z-index: 300; pointer-events: none; }
	.hp-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
	.hp-name { font-size: 15px; font-weight: 700; color: #232326; }
	.hp-email { font-size: 11px; color: #a1a1aa; }
	.hp-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
	.hp-tag { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; border: 1px solid; }
	.hp-tag.project { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }
	.hp-tag.agent { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
	.hp-tag.source { background: #f0fdf4; color: #166534; border-color: #bbf7d0; }
	.hp-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
	.hp-item { text-align: center; padding: 3px 0; }
	.hp-val { display: block; font-size: 14px; font-weight: 700; color: #232326; }
	.hp-label { display: block; font-size: 8px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; }

	.project-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
	.project-link { text-decoration: none; }
	.project-mini { background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 14px; transition: border-color 0.15s; }
	.project-mini:hover { border-color: #3b82f6; }
	.pm-name { font-size: 14px; font-weight: 700; color: #232326; font-family: monospace; margin-bottom: 4px; }
	.pm-stats { display: flex; gap: 10px; font-size: 11px; color: #70707a; }
	.pm-badge { display: inline-block; margin-top: 6px; font-size: 10px; font-weight: 600; color: #16a34a; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 1px 6px; border-radius: 4px; }

	.pie-inner { display: flex; align-items: center; gap: 20px; justify-content: center; padding: 8px 0; }
	.pie-svg { width: 120px; height: 120px; flex-shrink: 0; }
	.pie-legend { display: flex; flex-direction: column; gap: 6px; }
	.pie-leg-item { display: flex; align-items: center; gap: 8px; }
	.pie-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
	.pie-leg-name { font-size: 13px; font-weight: 600; color: #232326; font-family: monospace; }
	.pie-leg-val { font-size: 12px; color: #94a3b8; margin-left: auto; }

	@media (max-width: 768px) { .hero { grid-template-columns: repeat(2, 1fr); } .charts-grid { grid-template-columns: 1fr; } .hover-panel { display: none; } }
</style>
