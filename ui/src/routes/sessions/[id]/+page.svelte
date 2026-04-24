<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getSession, triggerAnalysis } from '$lib/api';
	import { renderMarkdown } from '$lib/markdown';
	import { fmtTokens, fmtDateRange, fmtNum, gradeColor, gradeBg } from '$lib/format';
	import type { QualityMetric } from '$lib/format';
	import type { SessionDetail } from '$lib/types';
	import ActivityCharts, { type ErrorDetail } from '$lib/components/ActivityCharts.svelte';
	import QualityBar from '$lib/components/QualityBar.svelte';
	import InsightLabel from '$lib/components/BehavioralTag.svelte';
	import MoodQuotes from '$lib/components/MoodQuotes.svelte';
	import type { MoodGroup } from '$lib/api';

	let session: SessionDetail | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let analyzing = $state(false);
	let toolsExpanded = $state(false);
	let errorsExpanded = $state(false);
	let hoverIdx: number | null = $state(null);
	let durHoverIdx: number | null = $state(null);
	let copied = $state(false);

	const id = $derived(page.params.id ?? '');

	const W = 720, H = 280;
	const PAD = { l: 52, r: 16, t: 16, b: 28 };
	const iW = W - PAD.l - PAD.r;
	const iH = H - PAD.t - PAD.b;

	function xOf(i: number, n: number): number { return PAD.l + (i / Math.max(n - 1, 1)) * iW; }

	function chartMove(e: MouseEvent, n: number, setter: (v: number) => void) {
		const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
		const relX = ((e.clientX - rect.left) / rect.width) * W;
		const idx = Math.round(((relX - PAD.l) / iW) * (n - 1));
		setter(Math.max(0, Math.min(n - 1, idx)));
	}

	onMount(async () => {
		try { session = await getSession(id); }
		catch (e) { error = e instanceof Error ? e.message : 'Failed to load session'; }
		finally { loading = false; }
	});

	async function reanalyze() {
		if (!session) return;
		analyzing = true;
		try { session = await triggerAnalysis(session.id); }
		catch (e) { error = e instanceof Error ? e.message : 'Analysis failed'; }
		finally { analyzing = false; }
	}

	function copyId() {
		if (!session) return;
		navigator.clipboard.writeText(session.id);
		copied = true;
		setTimeout(() => { copied = false; }, 1500);
	}

	function fmtSecs(ms: number): string {
		const s = ms / 1000;
		if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
		if (s >= 60) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
		return `${s.toFixed(1)}s`;
	}

	function wallMs(): number {
		if (!session?.end_time) return 0;
		return new Date(session.end_time).getTime() - new Date(session.start_time).getTime();
	}

	const activeMs = $derived.by(() => {
		if (!session?.context_growth) return 0;
		return session.context_growth.reduce((s, p) => s + (p.duration_ms ?? 0), 0);
	});

	const turnCount = $derived.by(() => session?.context_growth?.length ?? 0);
	const errorCount = $derived.by(() => {
		if (!session) return 0;
		// Use DB error_rate * total tool calls for accurate count (tool_calls array is capped)
		if (session.error_rate != null && session.total_tool_calls) {
			return Math.round(session.error_rate / 100 * session.total_tool_calls);
		}
		return session.tool_calls.filter(tc => !tc.success).length;
	});
	const errorRate = $derived.by(() => session?.error_rate ?? 0);

	const grade = $derived.by(() => {
		const rate = errorRate / 100;
		if (rate <= 0.05) return 'A';
		if (rate <= 0.10) return 'B';
		if (rate <= 0.20) return 'C';
		if (rate <= 0.35) return 'D';
		return 'F';
	});

	const toolDistribution = $derived.by(() => {
		if (!session) return {};
		const counts: Record<string, number> = {};
		for (const tc of session.tool_calls) counts[tc.tool_name] = (counts[tc.tool_name] ?? 0) + 1;
		return Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1]));
	});

	const errorTypes = $derived.by(() => {
		if (!session) return {};
		const counts: Record<string, number> = {};
		for (const tc of session.tool_calls) {
			if (!tc.success) counts[tc.tool_name] = (counts[tc.tool_name] ?? 0) + 1;
		}
		return Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1]));
	});

	const timeOfDay = $derived.by(() => {
		if (!session) return {};
		const counts: Record<string, number> = {};
		for (const tc of session.tool_calls) {
			const h = new Date(tc.timestamp).getHours();
			counts[h] = (counts[h] ?? 0) + 1;
		}
		return Object.fromEntries(Object.entries(counts).sort(([a], [b]) => Number(a) - Number(b)));
	});

	const languageDistribution = $derived.by(() => {
		if (!session) return {};
		const extToLang: Record<string, string> = {
			py: 'Python', go: 'Go', js: 'JavaScript', ts: 'TypeScript', tsx: 'TypeScript',
			jsx: 'JavaScript', rs: 'Rust', java: 'Java', rb: 'Ruby', php: 'PHP',
			c: 'C', cpp: 'C++', h: 'C/C++', cs: 'C#', swift: 'Swift', kt: 'Kotlin',
			scala: 'Scala', json: 'JSON', yaml: 'YAML', yml: 'YAML', toml: 'TOML',
			xml: 'XML', html: 'HTML', css: 'CSS', scss: 'CSS', md: 'Markdown',
			sql: 'SQL', sh: 'Shell', bash: 'Shell', zsh: 'Shell', dockerfile: 'Docker',
			tf: 'Terraform', svelte: 'Svelte', vue: 'Vue', j2: 'Jinja2', txt: 'Text',
		};
		const counts: Record<string, number> = {};
		const langTools = ['Read', 'Edit', 'Write', 'Glob', 'Grep'];
		for (const tc of session.tool_calls) {
			if (!langTools.includes(tc.tool_name) || !tc.input_value) continue;
			const ext = tc.input_value.match(/\.(\w{1,6})(?:['")\s,]|$)/)?.[1];
			if (!ext) continue;
			const lang = extToLang[ext.toLowerCase()];
			if (lang) counts[lang] = (counts[lang] ?? 0) + 1;
		}
		return Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1]));
	});

	const errorDetails = $derived.by((): ErrorDetail[] => {
		if (!session) return [];
		const groups: Record<string, { tool: string; message: string; count: number }> = {};
		for (const tc of session.tool_calls) {
			if (tc.success) continue;
			const msg = (tc.output_value ?? '').slice(0, 200).split('\n')[0] || 'Unknown error';
			const key = `${tc.tool_name}::${msg}`;
			if (groups[key]) {
				groups[key].count++;
			} else {
				groups[key] = { tool: tc.tool_name, message: msg, count: 1 };
			}
		}
		return Object.values(groups).sort((a, b) => b.count - a.count);
	});

	const firstEditMs = $derived.by(() => {
		if (!session) return null;
		const edit = session.tool_calls
			.filter(tc => tc.tool_name === 'Write' || tc.tool_name === 'Edit')
			.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())[0];
		if (!edit) return null;
		const ms = new Date(edit.timestamp).getTime() - new Date(session.start_time).getTime();
		return ms > 0 ? ms : null;
	});

	const toolsPerTurn = $derived.by(() => turnCount > 0 ? (session?.tool_calls?.length ?? 0) / turnCount : 0);

	const moodGroups = $derived.by((): MoodGroup[] => {
		if (!session?.notable_quotes) return [];
		const groups: Record<string, MoodGroup> = {};
		for (const q of session.notable_quotes) {
			const mood = (q.mood ?? q.vibe ?? 'unknown').toLowerCase();
			if (!groups[mood]) groups[mood] = { mood, quotes: [] };
			groups[mood].quotes.push({ quote: q.quote, mood, project: session.project_name, session_id: session.id });
		}
		return Object.values(groups);
	});

	const qualityMetrics = $derived.by((): QualityMetric[] => {
		if (!session) return [];
		const bl = session.baseline;
		const items: QualityMetric[] = [];

		function add(label: string, v: number | null, suffix: string, baselineKey?: string, higherIs?: 'better' | 'worse', fmt?: (n: number) => string) {
			if (v == null) return;
			const format = fmt ?? ((n: number) => fmtNum(n, suffix));
			const m: QualityMetric = { label, value: format(v) };
			if (bl && baselineKey && (bl as Record<string, number>)[baselineKey] != null) {
				const avg = (bl as Record<string, number>)[baselineKey];
				m.teamAvg = format(avg);
				if (higherIs) {
					const pct = Math.abs((v - avg) / (avg || 1)) * 100;
					if (pct > 15) {
						const above = v > avg;
						const isGood = higherIs === 'better' ? above : !above;
						m.deltaColor = isGood ? '#16a34a' : '#dc2626';
						m.deltaAbove = above;
					}
				}
			}
			items.push(m);
		}

		add('Read:Edit', session.read_edit_ratio, '', 'avg_read_edit_ratio', 'better');
		add('Blind edits', session.edits_without_read_pct, '%', 'avg_edits_without_read_pct', 'worse');
		add('Research:Mut', session.research_mutation_ratio, '', 'avg_research_mutation_ratio', 'better');
		add('Error rate', session.error_rate, '%', 'avg_error_rate', 'worse');
		add('Write vs Edit', session.write_vs_edit_pct, '%', 'avg_write_vs_edit_pct', 'worse');
		add('Thrashing', session.repeated_edits_count, '', 'avg_repeated_edits_count', 'worse');
		add('Ctx pressure', session.context_pressure_score, '', 'avg_context_pressure_score', 'worse');
		add('Tokens/edit', session.tokens_per_useful_edit, '', 'avg_tokens_per_useful_edit', 'worse', fmtTokens);
		const fmtInt = (n: number) => Math.round(n).toString();
		add('Error retries', session.error_retry_sequences, '', 'avg_error_retry_sequences', 'worse', fmtInt);
		add('Ctx resets', session.context_resets, '', 'avg_context_resets', 'worse', fmtInt);
		add('Dup reads', session.duplicate_read_count, '', 'avg_duplicate_read_count', 'worse', fmtInt);
		return items;
	});

	function categoryColor(cat: string): string {
		const m: Record<string, string> = { friction: '#dc2626', win: '#16a34a', recommendation: '#2563eb', pattern: '#7c3aed', skill_proposal: '#0891b2', summary: '#0f172a' };
		return m[cat] ?? '#64748b';
	}
	function categoryBg(cat: string): string {
		const m: Record<string, string> = { friction: '#fef2f2', win: '#f0fdf4', recommendation: '#eff6ff', pattern: '#faf5ff', skill_proposal: '#ecfeff', summary: '#f8fafc' };
		return m[cat] ?? '#f8fafc';
	}
	function categoryBorder(cat: string): string {
		const m: Record<string, string> = { friction: '#fca5a5', win: '#86efac', recommendation: '#93c5fd', pattern: '#c4b5fd', skill_proposal: '#67e8f9', summary: '#cbd5e1' };
		return m[cat] ?? '#e2e8f0';
	}
	function severityIcon(s: string): string { return s === 'critical' ? '!!' : s === 'warning' ? '!' : ''; }
	function categoryLabel(c: string): string { return c.replace('_', ' '); }

	const categoryOrder = ['summary', 'friction', 'win', 'recommendation', 'skill_proposal', 'pattern'];
	function sortedInsights(ins: SessionDetail['insights']) {
		return [...ins].sort((a, b) => categoryOrder.indexOf(a.category) - categoryOrder.indexOf(b.category));
	}
</script>

<svelte:head>
	<title>Session Detail - cinsights</title>
	<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css" />
</svelte:head>

<div class="nav-row">
	<a href="/sessions" class="back-link">&larr; Sessions</a>
	{#if session}
		<div style="display:flex; gap:10px; align-items:center;">
			<button class="reanalyze-btn" onclick={reanalyze} disabled={analyzing}>
				{analyzing ? 'Analyzing...' : 'Re-analyze'}
			</button>
		</div>
	{/if}
</div>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="error">{error}</div>
{:else if session}
	<!-- 1. Header -->
	<div class="session-header">
		<div class="sh-left">
			<button class="session-id-btn" onclick={copyId} title="Copy full session ID">
				<span class="mono">{session.id}</span>
				<span class="copy-icon">{copied ? '✓' : '⎘'}</span>
			</button>
			<span class="grade-badge" style="background: {gradeBg(grade)}; color: {gradeColor(grade)}">{grade}</span>
			<span class="status-pill" style="background: {session.status === 'analyzed' ? '#ecfdf5' : '#f5f3ff'}; color: {session.status === 'analyzed' ? '#16a34a' : '#7c3aed'}">
				{session.status}
			</span>
		</div>
		<div class="sh-right">
			{#if session.user_id}
				<a href="/sessions?user={session.user_id}" class="tag-link user">{session.user_id.split('@')[0]}</a>
			{/if}
			{#if session.project_name}
				<a href="/projects/{session.project_name}" class="tag-link project">{session.project_name}</a>
			{/if}
			<span class="tag-static">{fmtDateRange(session.start_time, session.end_time)}</span>
			{#if session.agent_version}
				<span class="tag-static mono">v{session.agent_version}</span>
			{/if}
			{#if session.effort_level}
				<span class="tag-static effort-{session.effort_level}">{session.effort_level}</span>
			{/if}
		</div>
	</div>

	<!-- 2. Hero Metrics -->
	<div class="hero">
		<div class="hero-metric">
			<div class="hero-value" style="color: #6366f1">{activeMs ? fmtSecs(activeMs) : fmtSecs(wallMs())}</div>
			<div class="hero-label">Active Time</div>
			<div class="hero-sub">{fmtSecs(wallMs())} wall clock</div>
		</div>
		<div class="hero-metric">
			<div class="hero-value" style="color: #8b5cf6">{turnCount}</div>
			<div class="hero-label">Turns</div>
			<div class="hero-sub">{toolsPerTurn.toFixed(1)} tools/turn</div>
		</div>
		<div class="hero-metric">
			<div class="hero-value" style="color: #3b82f6">{fmtTokens(session.total_tokens)}</div>
			<div class="hero-label">Total Tokens</div>
			<div class="hero-sub">{fmtTokens(session.prompt_tokens)} in / {fmtTokens(session.completion_tokens)} out</div>
		</div>
		<div class="hero-metric">
			<div class="hero-value" style="color: {errorRate > 15 ? '#dc2626' : errorRate > 5 ? '#f59e0b' : '#10b981'}">{session.total_tool_calls || session.tool_calls.length}</div>
			<div class="hero-label">Tool Calls</div>
			<div class="hero-sub">{errorCount} errors ({errorRate.toFixed(0)}%)</div>
		</div>
		<div class="hero-metric">
			<div class="hero-value" style="color: #64748b">{session.model ?? '-'}</div>
			<div class="hero-label">Model</div>
			<div class="hero-sub">{session.insights.length} insights</div>
		</div>
		{#if session.efficiency_score != null}
			{@const eff = session.efficiency_score}
			{@const effColor = eff > 80 ? '#10b981' : eff > 50 ? '#f59e0b' : '#dc2626'}
			<div class="hero-metric">
				<div class="hero-value" style="color: {effColor}">{Math.round(eff)}</div>
				<div class="hero-label">Efficiency</div>
				<div class="hero-sub">token efficiency score</div>
			</div>
		{/if}
	</div>

	<!-- 3. Quality Bar -->
	{#if qualityMetrics.length > 0}
		<QualityBar metrics={qualityMetrics} />
	{/if}

	<!-- Tasks & Turns -->
	<div class="section">
		<h2>Tasks & Turns</h2>

		<!-- Context Growth chart (tall, full-width) -->
		{#if session?.context_growth && session.context_growth.length > 1}
			{@const pts = session.context_growth}
			{@const n = pts.length}
			{@const maxY = Math.max(...pts.map(p => p.prompt_tokens), 1)}
			{@const yOf = (v: number) => PAD.t + iH - (v / maxY) * iH}
			{@const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xOf(i, n).toFixed(1)} ${yOf(p.prompt_tokens).toFixed(1)}`).join(' ')}
			{@const areaPath = `${linePath} L ${xOf(n-1, n).toFixed(1)} ${(PAD.t + iH).toFixed(1)} L ${xOf(0, n).toFixed(1)} ${(PAD.t + iH).toFixed(1)} Z`}
			{@const compactionIdxs = pts.map((p, i) => (i > 0 && p.prompt_tokens < pts[i-1].prompt_tokens * 0.85 ? i : -1)).filter(i => i >= 0)}
			{@const interruptIdxs = pts.map((p, i) => (p.interrupted ? i : -1)).filter(i => i >= 0)}
			{@const hover = hoverIdx !== null ? pts[hoverIdx] : null}
			<div class="chart-card">
				<div class="chart-header">
					<h3>Context Growth</h3>
					<div class="chart-header-right">
						{#if hover && hoverIdx !== null}
							<span class="chart-hover-val">Turn {hover.turn}: {fmtTokens(hover.prompt_tokens)}</span>
						{/if}
						{#if compactionIdxs.length > 0}
							<span class="trend-badge down">{compactionIdxs.length} compaction{compactionIdxs.length > 1 ? 's' : ''}</span>
						{/if}
						{#if interruptIdxs.length > 0}
							<span class="trend-badge interrupt">{interruptIdxs.length} interrupt{interruptIdxs.length > 1 ? 's' : ''}</span>
						{/if}
					</div>
				</div>
				<div class="chart-desc">Prompt tokens per turn (context window size)</div>
				<svg viewBox="0 0 {W} {H}" class="trend-svg"
					onmousemove={(e) => chartMove(e, n, v => hoverIdx = v)}
					onmouseleave={() => hoverIdx = null}>
					<defs>
						<linearGradient id="ctxG" x1="0" y1="0" x2="0" y2="1">
							<stop offset="0%" stop-color="#6366f1" stop-opacity="0.25" />
							<stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
						</linearGradient>
					</defs>
					{#each [0, 0.25, 0.5, 0.75, 1] as frac}
						{@const gy = PAD.t + iH * (1 - frac)}
						<line x1={PAD.l} x2={W - PAD.r} y1={gy} y2={gy} stroke="#f1f5f9" stroke-width="1" />
						<text x={PAD.l - 6} y={gy + 3} text-anchor="end" class="ax">{fmtTokens(Math.round(maxY * frac))}</text>
					{/each}
					<!-- Task bands -->
					{#if session?.tasks && session.tasks.length > 0}
						{@const taskColors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#3b82f6', '#84cc16']}
						{#each session.tasks as task, ti}
							{@const startIdx = pts.findIndex(p => p.turn >= task.start_turn)}
							{@const endIdx = pts.findIndex(p => p.turn > task.end_turn)}
							{@const si = startIdx >= 0 ? startIdx : 0}
							{@const ei = endIdx >= 0 ? endIdx : n}
							{@const x1 = xOf(si, n)}
							{@const x2 = xOf(Math.min(ei, n - 1), n)}
							<rect x={x1} y={PAD.t} width={Math.max(x2 - x1, 2)} height={iH} fill={taskColors[ti % taskColors.length]} opacity="0.08" />
							{#if x2 - x1 > 40}
								<text x={(x1 + x2) / 2} y={PAD.t + 10} text-anchor="middle" class="ax" fill={taskColors[ti % taskColors.length]} font-size="8" opacity="0.7">{task.name.slice(0, 20)}</text>
							{/if}
						{/each}
					{/if}
					<path d={areaPath} fill="url(#ctxG)" />
					<path d={linePath} fill="none" stroke="#6366f1" stroke-width="1.5" stroke-linejoin="round" />
					{#each compactionIdxs as i}
						<circle cx={xOf(i, n)} cy={yOf(pts[i].prompt_tokens)} r="3" fill="#f59e0b" stroke="white" stroke-width="1" />
					{/each}
					{#each interruptIdxs as i}
						<line x1={xOf(i, n)} x2={xOf(i, n)} y1={PAD.t} y2={PAD.t + iH} stroke="#ef4444" stroke-width="1" stroke-opacity="0.4" />
						<circle cx={xOf(i, n)} cy={yOf(pts[i].prompt_tokens)} r="3" fill="#ef4444" stroke="white" stroke-width="1" />
					{/each}
					{#if hoverIdx !== null}
						<line x1={xOf(hoverIdx, n)} x2={xOf(hoverIdx, n)} y1={PAD.t} y2={PAD.t + iH} stroke="#94a3b8" stroke-width="1" stroke-dasharray="2 2" />
						<circle cx={xOf(hoverIdx, n)} cy={yOf(pts[hoverIdx].prompt_tokens)} r="3.5" fill="#6366f1" stroke="white" stroke-width="1.5" />
					{/if}
					<rect x={PAD.l} y={PAD.t} width={iW} height={iH} fill="transparent" />
				</svg>
			</div>

			<!-- Turn Duration chart (tall, full-width) -->
			{#if session?.context_growth?.some(p => p.duration_ms != null)}
				{@const dPts = session!.context_growth!.filter(p => p.duration_ms != null)}
				{@const dn = dPts.length}
				{#if dn > 1}
					{@const durations = dPts.map(p => p.duration_ms!)}
					{@const maxD = Math.max(...durations, 1)}
					{@const sortedD = [...durations].sort((a, b) => a - b)}
					{@const median = sortedD[Math.floor(sortedD.length / 2)]}
					{@const dyOf = (v: number) => PAD.t + iH - (v / maxD) * iH}
					{@const dLine = dPts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xOf(i, dn).toFixed(1)} ${dyOf(p.duration_ms!).toFixed(1)}`).join(' ')}
					{@const dArea = `${dLine} L ${xOf(dn-1, dn).toFixed(1)} ${(PAD.t + iH).toFixed(1)} L ${xOf(0, dn).toFixed(1)} ${(PAD.t + iH).toFixed(1)} Z`}
					{@const slowIdxs = dPts.map((p, i) => (p.duration_ms! > median * 2 ? i : -1)).filter(i => i >= 0)}
					{@const dHover = durHoverIdx !== null ? dPts[durHoverIdx] : null}
					<div class="chart-card" style="margin-top: 14px">
						<div class="chart-header">
							<h3>Turn Duration</h3>
							<div class="chart-header-right">
								{#if dHover && durHoverIdx !== null}
									<span class="chart-hover-val">Turn {dHover.turn}: {fmtSecs(dHover.duration_ms!)}</span>
								{/if}
								<span class="chart-total">median {fmtSecs(median)}</span>
							</div>
						</div>
						<div class="chart-desc">Time per turn (slow turns highlighted)</div>
						<svg viewBox="0 0 {W} {H}" class="trend-svg"
							onmousemove={(e) => chartMove(e, dn, v => durHoverIdx = v)}
							onmouseleave={() => durHoverIdx = null}>
							<defs>
								<linearGradient id="durG" x1="0" y1="0" x2="0" y2="1">
									<stop offset="0%" stop-color="#10b981" stop-opacity="0.25" />
									<stop offset="100%" stop-color="#10b981" stop-opacity="0" />
								</linearGradient>
							</defs>
							{#each [0, 0.25, 0.5, 0.75, 1] as frac}
								{@const gy = PAD.t + iH * (1 - frac)}
								<line x1={PAD.l} x2={W - PAD.r} y1={gy} y2={gy} stroke="#f1f5f9" stroke-width="1" />
								<text x={PAD.l - 6} y={gy + 3} text-anchor="end" class="ax">{fmtSecs(maxD * frac)}</text>
							{/each}
							<path d={dArea} fill="url(#durG)" />
							<path d={dLine} fill="none" stroke="#10b981" stroke-width="1.5" stroke-linejoin="round" />
							<line x1={PAD.l} x2={W - PAD.r} y1={dyOf(median)} y2={dyOf(median)} stroke="#94a3b8" stroke-width="1" stroke-dasharray="4 3" />
							{#each slowIdxs as i}
								<circle cx={xOf(i, dn)} cy={dyOf(dPts[i].duration_ms!)} r="3" fill="#ef4444" stroke="white" stroke-width="1" />
							{/each}
							{#if durHoverIdx !== null}
								<line x1={xOf(durHoverIdx, dn)} x2={xOf(durHoverIdx, dn)} y1={PAD.t} y2={PAD.t + iH} stroke="#94a3b8" stroke-width="1" stroke-dasharray="2 2" />
								<circle cx={xOf(durHoverIdx, dn)} cy={dyOf(dPts[durHoverIdx].duration_ms!)} r="3.5" fill="#10b981" stroke="white" stroke-width="1.5" />
							{/if}
							<rect x={PAD.l} y={PAD.t} width={iW} height={iH} fill="transparent" />
						</svg>
					</div>
				{/if}
			{/if}
		{/if}

		<!-- Task list -->
		{#if session.tasks && session.tasks.length > 0}
			{@const totalTaskTokens = session.tasks.reduce((s, t) => s + t.prompt_tokens_total, 0) || 1}
			<div class="task-section-header">
				<span class="task-section-label">{session.tasks.length} tasks detected</span>
				{#if session.estimated_task_waste_tokens}
					<span class="waste-badge">{Math.round((session.estimated_task_waste_tokens / session.total_tokens) * 100)}% saveable</span>
				{/if}
			</div>
			<div class="task-list">
				{#each session.tasks as task}
					{@const pct = Math.max(3, (task.prompt_tokens_total / totalTaskTokens) * 100)}
					<div class="task-card">
						<div class="task-header">
							<span class="task-num">{task.task_number}.</span>
							<span class="task-name">{task.name}</span>
							<span class="task-turns">t{task.start_turn}-t{task.end_turn}</span>
						</div>
						<div class="task-desc">{task.description}</div>
						<div class="task-bar-row">
							<div class="task-bar" style="width: {pct}%"></div>
							<span class="task-meta">{fmtTokens(task.prompt_tokens_total)} tokens · {task.turn_count} turns</span>
							{#if task.estimated_waste_tokens && task.estimated_waste_tokens > 0}
								<span class="task-waste">~{fmtTokens(task.estimated_waste_tokens)} saveable</span>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}

		<!-- Token efficiency (waste breakdown inside Tasks section) -->
		{#if session.efficiency_score != null}
			{@const wasteItems = [
				{ label: 'Compaction cycles', value: session.compaction_cycle_waste, color: '#f59e0b' },
				{ label: 'Interrupted turns', value: session.interrupted_turn_waste, color: '#ef4444' },
				{ label: 'Repeated edits', value: session.repeated_edit_waste, color: '#8b5cf6' },
				{ label: 'Failed retries', value: session.failed_retry_waste, color: '#dc2626' },
				{ label: 'Task boundaries', value: session.estimated_task_waste_tokens, color: '#3b82f6' },
			].filter(w => w.value && w.value > 0)}
			{@const totalWaste = wasteItems.reduce((s, w) => s + (w.value ?? 0), 0)}
			{#if wasteItems.length > 0}
				<div class="efficiency-subsection">
					<h3 class="efficiency-subtitle">Token Efficiency</h3>
					<div class="efficiency-grid">
						{#each wasteItems as w}
							{@const wpct = Math.round((w.value! / session.total_tokens) * 100)}
							<div class="waste-card">
								<div class="waste-dot" style="background: {w.color}"></div>
								<div class="waste-info">
									<div class="waste-label">{w.label}</div>
									<div class="waste-value">{fmtTokens(w.value!)} <span class="waste-pct">({wpct}%)</span></div>
								</div>
							</div>
						{/each}
						<div class="waste-card waste-total">
							<div class="waste-info">
								<div class="waste-label">Total saveable</div>
								<div class="waste-value">{fmtTokens(totalWaste)} <span class="waste-pct">({Math.round((totalWaste / session.total_tokens) * 100)}%)</span></div>
							</div>
						</div>
					</div>
					{#if session.floor_drift_score != null && session.floor_drift_score > 0.3}
						<div class="efficiency-rec">Post-compaction floor is growing — stale context is accumulating across compactions.</div>
					{/if}
					{#if session.task_count && session.task_count > 5 && session.estimated_task_waste_tokens && session.estimated_task_waste_tokens > 0}
						<div class="efficiency-rec">This session had {session.task_count} tasks. Starting new sessions per task could save ~{fmtTokens(session.estimated_task_waste_tokens)} tokens.</div>
					{/if}
				</div>
			{/if}
		{/if}
	</div>

	<!-- Activity -->
	<div class="section">
		<h2>Activity</h2>
		<ActivityCharts {toolDistribution} {languageDistribution} {timeOfDay} {errorTypes} errorDetails={[]} />
	</div>

	<!-- 5. Notable Quotes -->
	{#if moodGroups.length > 0}
		<MoodQuotes {moodGroups} />
	{/if}

	<!-- 6. Insights -->
	{#if session.insights.length > 0}
		<div class="section">
			<h2>Insights <span class="h2-count">{session.insights.length}</span></h2>
			<div class="insights-grid">
				{#each sortedInsights(session.insights) as insight}
					<div class="insight-card" style="background: {categoryBg(insight.category)}; border-color: {categoryBorder(insight.category)};">
						<div class="insight-header">
							<span class="insight-category" style="color: {categoryColor(insight.category)}">{categoryLabel(insight.category)}</span>
							{#if insight.label}
								<InsightLabel label={insight.label} />
							{/if}
							{#if severityIcon(insight.severity)}
								<span class="severity-badge severity-{insight.severity}">{severityIcon(insight.severity)}</span>
							{/if}
						</div>
						<h3 class="insight-title">{insight.title}</h3>
						<div class="insight-content markdown-body">{@html renderMarkdown(insight.content)}</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}
		<div class="empty">No insights yet. Click "Re-analyze" to generate insights.</div>
	{/if}

	<!-- 7. Errors (collapsed) -->
	{#if errorDetails.length > 0}
		<div class="section">
			<button class="collapse-btn" onclick={() => errorsExpanded = !errorsExpanded}>
				<span class="collapse-arrow" class:open={errorsExpanded}>&#9654;</span>
				<h2 style="display:inline; margin-bottom:0">Errors <span class="h2-count">{errorCount}</span></h2>
			</button>
			{#if errorsExpanded}
				<div class="error-list">
					{#each errorDetails as err}
						<div class="error-item">
							<span class="error-tool-name">{err.tool}</span>
							<span class="error-count">{err.count}x</span>
							<span class="error-msg">{err.message}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- 8. Tool Calls (collapsed) -->
	{#if session.tool_calls.length > 0}
		<div class="section">
			<button class="collapse-btn" onclick={() => toolsExpanded = !toolsExpanded}>
				<span class="collapse-arrow" class:open={toolsExpanded}>&#9654;</span>
				<h2 style="display:inline; margin-bottom:0">Tool Calls <span class="h2-count">{session.tool_calls.length}{#if session.total_tool_calls > session.tool_calls.length} of {session.total_tool_calls}{/if}</span></h2>
			</button>
			{#if toolsExpanded}
				<div class="tool-list">
					{#each session.tool_calls as tc}
						<div class="tool-item" class:error-tool={!tc.success}>
							<div class="tool-header">
								<span class="tool-name">{tc.tool_name}</span>
								<span class="tool-meta">
									{#if tc.duration_ms}{tc.duration_ms.toFixed(0)}ms{/if}
									{#if !tc.success}<span class="tool-error">ERROR</span>{/if}
								</span>
							</div>
							{#if tc.input_value}
								<details class="tool-io"><summary>Input</summary><pre>{tc.input_value}</pre></details>
							{/if}
							{#if tc.output_value}
								<details class="tool-io"><summary>Output</summary><pre>{tc.output_value}</pre></details>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
{/if}

<style>
	.nav-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
	.back-link { color: #64748b; text-decoration: none; font-size: 14px; }
	.back-link:hover { color: #2563eb; }
	.loading, .error { text-align: center; padding: 48px; color: #64748b; }
	.error { color: #dc2626; }

	.session-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
	.sh-left { display: flex; align-items: center; gap: 10px; }
	.sh-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
	.session-id-btn {
		display: flex; align-items: center; gap: 6px; background: #f8fafc; border: 1px solid #e2e8f0;
		border-radius: 8px; padding: 6px 12px; cursor: pointer; transition: border-color 0.15s;
	}
	.session-id-btn:hover { border-color: #3b82f6; }
	.session-id-btn .mono { font-size: 12px; color: #334155; font-family: 'SF Mono', 'Fira Code', monospace; }
	.copy-icon { font-size: 14px; color: #94a3b8; }
	.status-pill { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 100px; text-transform: uppercase; letter-spacing: 0.04em; }
	.tag-link { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 6px; text-decoration: none; transition: opacity 0.15s; }
	.tag-link:hover { opacity: 0.8; }
	.tag-link.user { background: #fef3c7; color: #92400e; }
	.tag-link.project { background: #eff6ff; color: #2563eb; }
	.tag-static { font-size: 12px; color: #94a3b8; }

	.hero { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 14px; margin-bottom: 20px; }
	.hero-metric {
		background: white; border-radius: 16px; padding: 20px 18px; text-align: center;
		border: 1px solid #e8e5e0; transition: transform 0.2s, box-shadow 0.2s;
	}
	.hero-metric:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
	.hero-value { font-size: 28px; font-weight: 800; letter-spacing: -1.5px; line-height: 1; font-variant-numeric: tabular-nums; }
	.hero-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #70707a; margin-top: 6px; }
	.hero-sub { font-size: 11px; color: #a1a1aa; margin-top: 2px; }

	.grade-badge { font-size: 18px; font-weight: 800; padding: 2px 12px; border-radius: 10px; }

	.chart-card { background: white; border-radius: 16px; padding: 22px 24px; }
	.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1px; }
	.chart-header h3 { font-size: 14px; font-weight: 700; color: #232326; }
	.chart-header-right { display: flex; align-items: center; gap: 6px; }
	.chart-hover-val { font-size: 12px; color: #475569; }
	.chart-desc { font-size: 11px; color: #a1a1aa; margin-bottom: 8px; }
	.chart-total { font-size: 11px; font-weight: 600; color: #10b981; }
	.trend-badge { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 5px; }
	.trend-badge.down { background: #fef3c7; color: #92400e; }
	.trend-badge.interrupt { background: #fef2f2; color: #dc2626; }
	.effort-high, .effort-max { color: #16a34a; font-weight: 600; }
	.effort-medium { color: #d97706; font-weight: 600; }
	.effort-low { color: #94a3b8; }
	.trend-svg { width: 100%; height: auto; cursor: crosshair; }
	.ax { font-size: 10px; fill: #94a3b8; font-family: inherit; }

	.reanalyze-btn {
		background: #2563eb; color: white; border: none; border-radius: 8px;
		padding: 7px 16px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.15s;
	}
	.reanalyze-btn:hover { background: #1d4ed8; }
	.reanalyze-btn:disabled { background: #94a3b8; cursor: not-allowed; }

	.section { margin-bottom: 28px; }
	h2 { font-size: 18px; font-weight: 600; color: #0f172a; margin-bottom: 16px; }
	.h2-count { font-size: 13px; font-weight: 500; color: #94a3b8; }

	.insights-grid { display: flex; flex-direction: column; gap: 14px; }
	.insight-card { border: 1px solid; border-radius: 12px; padding: 20px; }
	.insight-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
	.insight-category { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
	.severity-badge { font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
	.severity-critical { background: #fef2f2; color: #dc2626; }
	.severity-warning { background: #fefce8; color: #ca8a04; }
	.insight-title { font-size: 16px; font-weight: 600; color: #0f172a; margin-bottom: 10px; }
	.insight-content { font-size: 14px; color: #334155; line-height: 1.7; }
	.insight-content :global(p) { margin-bottom: 10px; }
	.insight-content :global(p:last-child) { margin-bottom: 0; }
	.insight-content :global(ul), .insight-content :global(ol) { margin: 8px 0; padding-left: 24px; }
	.insight-content :global(li) { margin-bottom: 4px; }
	.insight-content :global(strong) { font-weight: 600; color: #0f172a; }
	.insight-content :global(code) { background: rgba(0,0,0,0.06); padding: 1px 5px; border-radius: 3px; font-size: 13px; font-family: 'SF Mono', 'Fira Code', monospace; }
	.insight-content :global(pre) { margin: 10px 0; padding: 12px 16px; background: #f1f5f9; border-radius: 6px; overflow-x: auto; border: 1px solid #e2e8f0; }
	.insight-content :global(pre code) { background: none; padding: 0; font-size: 12px; line-height: 1.5; }
	.insight-content :global(blockquote) { margin: 10px 0; padding: 8px 16px; border-left: 3px solid #cbd5e1; color: #64748b; background: rgba(0,0,0,0.02); border-radius: 0 4px 4px 0; }
	.insight-content :global(a) { color: #2563eb; text-decoration: none; }
	.insight-content :global(a:hover) { text-decoration: underline; }

	.error-list { display: flex; flex-direction: column; gap: 6px; }
	.error-item { display: flex; align-items: baseline; gap: 8px; padding: 8px 12px; background: #fff5f5; border: 1px solid #fecaca; border-radius: 8px; font-size: 13px; }
	.error-tool-name { font-weight: 600; font-family: monospace; color: #dc2626; min-width: 80px; }
	.error-count { font-weight: 700; font-size: 11px; color: #92400e; background: #fef3c7; padding: 1px 5px; border-radius: 3px; }
	.error-msg { color: #71717a; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 500px; }

	.collapse-btn { background: none; border: none; cursor: pointer; display: flex; align-items: center; gap: 8px; padding: 0; margin-bottom: 12px; }
	.collapse-arrow { font-size: 10px; color: #94a3b8; transition: transform 0.15s; }
	.collapse-arrow.open { transform: rotate(90deg); }
	.tool-list { display: flex; flex-direction: column; gap: 8px; }
	.tool-item { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; }
	.tool-item.error-tool { border-color: #fca5a5; background: #fff5f5; }
	.tool-header { display: flex; justify-content: space-between; align-items: center; }
	.tool-name { font-weight: 600; font-size: 13px; font-family: monospace; }
	.tool-meta { font-size: 12px; color: #64748b; display: flex; gap: 8px; align-items: center; }
	.tool-error { color: #dc2626; font-weight: 700; font-size: 11px; }
	.tool-io { margin-top: 8px; }
	.tool-io summary { font-size: 12px; color: #64748b; cursor: pointer; }
	.tool-io pre { margin-top: 4px; padding: 8px; background: #f8fafc; border-radius: 4px; font-size: 11px; overflow-x: auto; max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
	.empty { padding: 32px; text-align: center; color: #64748b; background: white; border: 1px solid #e2e8f0; border-radius: 12px; }

	/* Tasks & Turns */
	.task-section-header { display: flex; align-items: center; gap: 10px; margin: 20px 0 10px; }
	.task-section-label { font-size: 13px; font-weight: 600; color: #64748b; }
	.task-list { display: flex; flex-direction: column; gap: 10px; }
	.task-card { background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 14px 18px; }
	.task-header { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }
	.task-num { font-weight: 700; color: #94a3b8; font-size: 13px; }
	.task-name { font-weight: 600; font-size: 14px; color: #0f172a; }
	.task-turns { font-size: 11px; color: #94a3b8; margin-left: auto; font-family: 'SF Mono', 'Fira Code', monospace; }
	.task-desc { font-size: 12px; color: #64748b; margin-bottom: 8px; }
	.task-bar-row { display: flex; align-items: center; gap: 10px; }
	.task-bar { height: 4px; background: #6366f1; border-radius: 2px; min-width: 4px; }
	.task-meta { font-size: 11px; color: #94a3b8; }
	.task-waste { font-size: 11px; color: #dc2626; font-weight: 600; margin-left: auto; }
	.waste-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 5px; background: #fef2f2; color: #dc2626; }

	/* Token Efficiency (inside Tasks section) */
	.efficiency-subsection { margin-top: 20px; }
	.efficiency-subtitle { font-size: 14px; font-weight: 700; color: #232326; margin-bottom: 10px; }
	.efficiency-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-bottom: 12px; }
	.waste-card { display: flex; align-items: center; gap: 10px; background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 12px 14px; }
	.waste-card.waste-total { background: #f8fafc; border-color: #cbd5e1; }
	.waste-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
	.waste-info { display: flex; flex-direction: column; }
	.waste-label { font-size: 11px; color: #64748b; }
	.waste-value { font-size: 14px; font-weight: 700; color: #0f172a; }
	.waste-pct { font-size: 11px; font-weight: 500; color: #94a3b8; }
	.efficiency-rec { font-size: 13px; color: #64748b; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 14px; margin-top: 8px; }

	@media (max-width: 768px) {
		.session-header { flex-direction: column; align-items: flex-start; }
		.efficiency-grid { grid-template-columns: 1fr; }
	}
</style>
