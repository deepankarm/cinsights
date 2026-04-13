<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getSession, triggerAnalysis } from '$lib/api';
	import { renderMarkdown } from '$lib/markdown';
	import type { SessionDetail } from '$lib/types';

	let session: SessionDetail | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let analyzing = $state(false);
	let toolsExpanded = $state(false);
	let hoverIdx: number | null = $state(null);
	let durHoverIdx: number | null = $state(null);

	const id = $derived(page.params.id);

	const CHART_W = 720;
	const CHART_H = 220;
	const CHART_PAD = { l: 52, r: 16, t: 14, b: 28 };

	function handleChartMove(e: MouseEvent & { currentTarget: SVGSVGElement }, len: number) {
		const rect = e.currentTarget.getBoundingClientRect();
		const xView = ((e.clientX - rect.left) / rect.width) * CHART_W;
		const innerW = CHART_W - CHART_PAD.l - CHART_PAD.r;
		const frac = (xView - CHART_PAD.l) / innerW;
		const idx = Math.round(frac * (len - 1));
		hoverIdx = Math.max(0, Math.min(len - 1, idx));
	}

	onMount(async () => {
		try {
			session = await getSession(id);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load session';
		} finally {
			loading = false;
		}
	});

	async function reanalyze() {
		if (!session) return;
		analyzing = true;
		try {
			session = await triggerAnalysis(session.id);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Analysis failed';
		} finally {
			analyzing = false;
		}
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString();
	}

	function formatDuration(start: string, end: string | null): string {
		if (!end) return '-';
		const ms = new Date(end).getTime() - new Date(start).getTime();
		const mins = Math.floor(ms / 60000);
		const secs = Math.floor((ms % 60000) / 1000);
		if (mins > 0) return `${mins}m ${secs}s`;
		return `${secs}s`;
	}

	function formatTokens(n: number): string {
		if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
		if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
		return n.toString();
	}

	function formatSecs(ms: number): string {
		const s = ms / 1000;
		if (s >= 60) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
		return `${s.toFixed(1)}s`;
	}

	function categoryColor(cat: string): string {
		switch (cat) {
			case 'friction':
				return '#dc2626';
			case 'win':
				return '#16a34a';
			case 'recommendation':
				return '#2563eb';
			case 'pattern':
				return '#7c3aed';
			case 'skill_proposal':
				return '#0891b2';
			case 'summary':
				return '#0f172a';
			default:
				return '#64748b';
		}
	}

	function categoryBg(cat: string): string {
		switch (cat) {
			case 'friction':
				return '#fef2f2';
			case 'win':
				return '#f0fdf4';
			case 'recommendation':
				return '#eff6ff';
			case 'pattern':
				return '#faf5ff';
			case 'skill_proposal':
				return '#ecfeff';
			case 'summary':
				return '#f8fafc';
			default:
				return '#f8fafc';
		}
	}

	function categoryBorder(cat: string): string {
		switch (cat) {
			case 'friction':
				return '#fca5a5';
			case 'win':
				return '#86efac';
			case 'recommendation':
				return '#93c5fd';
			case 'pattern':
				return '#c4b5fd';
			case 'skill_proposal':
				return '#67e8f9';
			case 'summary':
				return '#cbd5e1';
			default:
				return '#e2e8f0';
		}
	}

	function severityIcon(severity: string): string {
		switch (severity) {
			case 'critical':
				return '!!';
			case 'warning':
				return '!';
			default:
				return '';
		}
	}

	function categoryLabel(cat: string): string {
		return cat.replace('_', ' ');
	}

	const activeTime = $derived.by(() => {
		if (!session?.context_growth) return null;
		const totalMs = session.context_growth.reduce((sum, p) => sum + (p.duration_ms ?? 0), 0);
		if (totalMs === 0) return null;
		return formatSecs(totalMs);
	});

	const firstEditCall = $derived.by(() => {
		if (!session) return null;
		const edits = session.tool_calls
			.filter((tc) => tc.tool_name === 'Write' || tc.tool_name === 'Edit')
			.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
		return edits[0] ?? null;
	});

	const firstEditMs = $derived(
		firstEditCall && session
			? new Date(firstEditCall.timestamp).getTime() - new Date(session.start_time).getTime()
			: null
	);

	// Group insights by category for display order
	const categoryOrder = ['summary', 'friction', 'win', 'recommendation', 'skill_proposal', 'pattern'];

	function sortedInsights(insights: SessionDetail['insights']) {
		return [...insights].sort(
			(a, b) => categoryOrder.indexOf(a.category) - categoryOrder.indexOf(b.category)
		);
	}
</script>

<svelte:head>
	<title>Session Detail - cinsights</title>
	<link
		rel="stylesheet"
		href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css"
	/>
</svelte:head>

<div class="nav-row">
	<a href="/sessions" class="back-link">&larr; Back to sessions</a>
	<a href="/report" class="back-link">View Report &rarr;</a>
</div>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="error">{error}</div>
{:else if session}
	<!-- Session Metadata -->
	<div class="meta-card">
		<div class="meta-row">
			<div class="meta-item">
				<span class="meta-label">Session</span>
				<span class="meta-value mono">{session.id.slice(0, 8)}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">User</span>
				<span class="meta-value mono">{session.user_id ?? '-'}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Project</span>
				<span class="meta-value mono">{session.project_name ?? '-'}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Model</span>
				<span class="meta-value mono">{session.model ?? '-'}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Active Time</span>
				<span class="meta-value">{activeTime ?? formatDuration(session.start_time, session.end_time)}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Started</span>
				<span class="meta-value">{formatDate(session.start_time)}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Time Span</span>
				<span class="meta-value">{formatDuration(session.start_time, session.end_time)}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Tokens</span>
				<span class="meta-value">{formatTokens(session.total_tokens)}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Tool Calls</span>
				<span class="meta-value">{session.tool_calls.length}</span>
			</div>
			<div class="meta-item">
				<span class="meta-label">Status</span>
				<span
					class="meta-value"
					style="text-transform: uppercase; font-size: 12px; font-weight: 600;"
				>
					{session.status}
				</span>
			</div>
			{#if firstEditMs != null && firstEditMs > 0}
				<div class="meta-item">
					<span class="meta-label">First Edit</span>
					<span class="meta-value">{formatSecs(firstEditMs)} in</span>
				</div>
			{/if}
		</div>
		<button class="reanalyze-btn" onclick={reanalyze} disabled={analyzing}>
			{analyzing ? 'Analyzing...' : 'Re-analyze'}
		</button>
	</div>

	<!-- Context Growth -->
	{#if session.context_growth && session.context_growth.length > 1}
		{@const pts = session.context_growth}
		{@const n = pts.length}
		{@const maxY = Math.max(...pts.map((p) => p.prompt_tokens), 1)}
		{@const innerW = CHART_W - CHART_PAD.l - CHART_PAD.r}
		{@const innerH = CHART_H - CHART_PAD.t - CHART_PAD.b}
		{@const xOf = (i: number) => CHART_PAD.l + (i / (n - 1)) * innerW}
		{@const yOf = (v: number) => CHART_PAD.t + innerH - (v / maxY) * innerH}
		{@const step = Math.max(1, Math.ceil(n / 8))}
		{@const tickIdxs = pts
			.map((_, i) => i)
			.filter((i) => i === 0 || i === n - 1 || i % step === 0)}
		{@const linePath = pts
			.map(
				(p, i) =>
					`${i === 0 ? 'M' : 'L'} ${xOf(i).toFixed(1)} ${yOf(p.prompt_tokens).toFixed(1)}`
			)
			.join(' ')}
		{@const baselineY = (CHART_PAD.t + innerH).toFixed(1)}
		{@const areaPath = `${linePath} L ${xOf(n - 1).toFixed(1)} ${baselineY} L ${xOf(0).toFixed(1)} ${baselineY} Z`}
		{@const compactionIdxs = pts
			.map((p, i) => (i > 0 && p.prompt_tokens < pts[i - 1].prompt_tokens * 0.85 ? i : -1))
			.filter((i) => i >= 0)}
		{@const hover = hoverIdx !== null ? pts[hoverIdx] : null}
		<div class="section">
			<h2>Context Growth</h2>
			<div class="context-chart">
				<div class="chart-inner">
					<svg
						viewBox="0 0 {CHART_W} {CHART_H}"
						class="context-svg"
						role="img"
						aria-label="Context growth over turns"
						onmousemove={(e) => handleChartMove(e, n)}
						onmouseleave={() => (hoverIdx = null)}
					>
						<defs>
							<linearGradient id="ctxArea" x1="0" y1="0" x2="0" y2="1">
								<stop offset="0%" stop-color="#6366f1" stop-opacity="0.35" />
								<stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
							</linearGradient>
						</defs>

						<!-- Gridlines + Y labels -->
						{#each [0, 0.5, 1] as frac}
							{@const gy = CHART_PAD.t + innerH * (1 - frac)}
							<line
								x1={CHART_PAD.l}
								x2={CHART_W - CHART_PAD.r}
								y1={gy}
								y2={gy}
								stroke="#f1f5f9"
								stroke-width="1"
							/>
							<text x={CHART_PAD.l - 6} y={gy + 3} text-anchor="end" class="axis-text">
								{formatTokens(Math.round(maxY * frac))}
							</text>
						{/each}

						<!-- Area + line -->
						<path d={areaPath} fill="url(#ctxArea)" />
						<path
							d={linePath}
							fill="none"
							stroke="#6366f1"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>

						<!-- Compaction markers -->
						{#each compactionIdxs as i}
							<circle
								cx={xOf(i)}
								cy={yOf(pts[i].prompt_tokens)}
								r="3"
								fill="#f59e0b"
								stroke="white"
								stroke-width="1"
							/>
						{/each}

						<!-- X ticks -->
						{#each tickIdxs as i}
							<text x={xOf(i)} y={CHART_H - 10} text-anchor="middle" class="axis-text">
								{pts[i].turn}
							</text>
						{/each}

						<!-- Hover marker -->
						{#if hover && hoverIdx !== null}
							<line
								x1={xOf(hoverIdx)}
								x2={xOf(hoverIdx)}
								y1={CHART_PAD.t}
								y2={CHART_PAD.t + innerH}
								stroke="#94a3b8"
								stroke-width="1"
								stroke-dasharray="2 2"
							/>
							<circle
								cx={xOf(hoverIdx)}
								cy={yOf(hover.prompt_tokens)}
								r="3.5"
								fill="#6366f1"
								stroke="white"
								stroke-width="1.5"
							/>
						{/if}

						<!-- Invisible hit area covering full plot (ensures mousemove fires across gaps) -->
						<rect
							x={CHART_PAD.l}
							y={CHART_PAD.t}
							width={innerW}
							height={innerH}
							fill="transparent"
						/>
					</svg>

					{#if hover && hoverIdx !== null}
						{@const leftPct = (xOf(hoverIdx) / CHART_W) * 100}
						{@const topPct = (yOf(hover.prompt_tokens) / CHART_H) * 100}
						<div
							class="chart-tooltip"
							class:flip-left={leftPct < 15}
							class:flip-right={leftPct > 85}
							style="left: {leftPct}%; top: {topPct}%;"
						>
							<div class="tt-turn">Turn {hover.turn}</div>
							<div class="tt-row">
								<span class="tt-dot prompt"></span>{formatTokens(hover.prompt_tokens)} prompt
							</div>
							<div class="tt-row">
								<span class="tt-dot completion"></span>{formatTokens(hover.completion_tokens)} completion
							</div>
						</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}

	<!-- Turn Duration -->
	{#if session.context_growth && session.context_growth.some((p) => p.duration_ms != null)}
		{@const pts = session.context_growth.filter((p) => p.duration_ms != null)}
		{@const n = pts.length}
		{#if n > 1}
			{@const durations = pts.map((p) => p.duration_ms!)}
			{@const maxD = Math.max(...durations, 1)}
			{@const sortedD = [...durations].sort((a, b) => a - b)}
			{@const median = sortedD[Math.floor(sortedD.length / 2)]}
			{@const innerW = CHART_W - CHART_PAD.l - CHART_PAD.r}
			{@const innerH = CHART_H - CHART_PAD.t - CHART_PAD.b}
			{@const xOf = (i: number) => CHART_PAD.l + (i / (n - 1)) * innerW}
			{@const yOf = (v: number) => CHART_PAD.t + innerH - (v / maxD) * innerH}
			{@const step = Math.max(1, Math.ceil(n / 8))}
			{@const tickIdxs = pts
				.map((_, i) => i)
				.filter((i) => i === 0 || i === n - 1 || i % step === 0)}
			{@const linePath = pts
				.map(
					(p, i) =>
						`${i === 0 ? 'M' : 'L'} ${xOf(i).toFixed(1)} ${yOf(p.duration_ms!).toFixed(1)}`
				)
				.join(' ')}
			{@const baselineY = (CHART_PAD.t + innerH).toFixed(1)}
			{@const areaPath = `${linePath} L ${xOf(n - 1).toFixed(1)} ${baselineY} L ${xOf(0).toFixed(1)} ${baselineY} Z`}
			{@const slowIdxs = pts
				.map((p, i) => (p.duration_ms! > median * 2 ? i : -1))
				.filter((i) => i >= 0)}
			{@const durHover = durHoverIdx !== null ? pts[durHoverIdx] : null}
			<div class="section">
				<h2>Turn Duration</h2>
				<div class="context-chart">
					<div class="chart-inner">
						<svg
							viewBox="0 0 {CHART_W} {CHART_H}"
							class="context-svg"
							role="img"
							aria-label="Turn duration over turns"
							onmousemove={(e) => {
								const rect = e.currentTarget.getBoundingClientRect();
								const xView = ((e.clientX - rect.left) / rect.width) * CHART_W;
								const frac = (xView - CHART_PAD.l) / innerW;
								const idx = Math.round(frac * (n - 1));
								durHoverIdx = Math.max(0, Math.min(n - 1, idx));
							}}
							onmouseleave={() => (durHoverIdx = null)}
						>
							<defs>
								<linearGradient id="durArea" x1="0" y1="0" x2="0" y2="1">
									<stop offset="0%" stop-color="#10b981" stop-opacity="0.35" />
									<stop offset="100%" stop-color="#10b981" stop-opacity="0" />
								</linearGradient>
							</defs>

							{#each [0, 0.5, 1] as frac}
								{@const gy = CHART_PAD.t + innerH * (1 - frac)}
								<line
									x1={CHART_PAD.l}
									x2={CHART_W - CHART_PAD.r}
									y1={gy}
									y2={gy}
									stroke="#f1f5f9"
									stroke-width="1"
								/>
								<text x={CHART_PAD.l - 6} y={gy + 3} text-anchor="end" class="axis-text">
									{formatSecs(maxD * frac)}
								</text>
							{/each}

							<path d={areaPath} fill="url(#durArea)" />
							<path
								d={linePath}
								fill="none"
								stroke="#10b981"
								stroke-width="1.5"
								stroke-linejoin="round"
							/>

							{#each slowIdxs as i}
								<circle
									cx={xOf(i)}
									cy={yOf(pts[i].duration_ms!)}
									r="3"
									fill="#ef4444"
									stroke="white"
									stroke-width="1"
								/>
							{/each}

							{#each tickIdxs as i}
								<text x={xOf(i)} y={CHART_H - 10} text-anchor="middle" class="axis-text">
									{pts[i].turn}
								</text>
							{/each}

							{#if durHover && durHoverIdx !== null}
								<line
									x1={xOf(durHoverIdx)}
									x2={xOf(durHoverIdx)}
									y1={CHART_PAD.t}
									y2={CHART_PAD.t + innerH}
									stroke="#94a3b8"
									stroke-width="1"
									stroke-dasharray="2 2"
								/>
								<circle
									cx={xOf(durHoverIdx)}
									cy={yOf(durHover.duration_ms!)}
									r="3.5"
									fill="#10b981"
									stroke="white"
									stroke-width="1.5"
								/>
							{/if}

							<rect
								x={CHART_PAD.l}
								y={CHART_PAD.t}
								width={innerW}
								height={innerH}
								fill="transparent"
							/>
						</svg>

						{#if durHover && durHoverIdx !== null}
							{@const leftPct = (xOf(durHoverIdx) / CHART_W) * 100}
							{@const topPct = (yOf(durHover.duration_ms!) / CHART_H) * 100}
							<div
								class="chart-tooltip"
								class:flip-left={leftPct < 15}
								class:flip-right={leftPct > 85}
								style="left: {leftPct}%; top: {topPct}%;"
							>
								<div class="tt-turn">Turn {durHover.turn}</div>
								<div class="tt-row">
									<span class="tt-dot duration"></span>{formatSecs(durHover.duration_ms!)}
								</div>
								{#if durHover.duration_ms! > median * 2}
									<div class="tt-row slow">&gt;2x median</div>
								{/if}
							</div>
						{/if}
					</div>
				</div>
			</div>
		{/if}
	{/if}

	<!-- Insights -->
	{#if session.insights.length > 0}
		<div class="section">
			<h2>Insights ({session.insights.length})</h2>
			<div class="insights-grid">
				{#each sortedInsights(session.insights) as insight}
					<div
						class="insight-card"
						style="background: {categoryBg(insight.category)}; border-color: {categoryBorder(insight.category)};"
					>
						<div class="insight-header">
							<span
								class="insight-category"
								style="color: {categoryColor(insight.category)}"
							>
								{categoryLabel(insight.category)}
							</span>
							{#if severityIcon(insight.severity)}
								<span class="severity-badge severity-{insight.severity}">
									{severityIcon(insight.severity)}
								</span>
							{/if}
						</div>
						<h3 class="insight-title">{insight.title}</h3>
						<div class="insight-content markdown-body">
							{@html renderMarkdown(insight.content)}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}
		<div class="empty">No insights yet. Click "Re-analyze" to generate insights.</div>
	{/if}

	<!-- Tool Calls -->
	{#if session.tool_calls.length > 0}
		<div class="section">
			<button class="collapse-btn" onclick={() => (toolsExpanded = !toolsExpanded)}>
				<span class="collapse-arrow" class:open={toolsExpanded}>&#9654;</span>
				<h2 style="display:inline">Tool Calls ({session.tool_calls.length})</h2>
			</button>
			{#if toolsExpanded}
				<div class="tool-list">
					{#each session.tool_calls as tc}
						<div class="tool-item" class:error-tool={!tc.success}>
							<div class="tool-header">
								<span class="tool-name">{tc.tool_name}</span>
								<span class="tool-meta">
									{#if tc.duration_ms}
										{tc.duration_ms.toFixed(0)}ms
									{/if}
									{#if !tc.success}
										<span class="tool-error">ERROR</span>
									{/if}
								</span>
							</div>
							{#if tc.input_value}
								<details class="tool-io">
									<summary>Input</summary>
									<pre>{tc.input_value}</pre>
								</details>
							{/if}
							{#if tc.output_value}
								<details class="tool-io">
									<summary>Output</summary>
									<pre>{tc.output_value}</pre>
								</details>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
{/if}

<style>
	.nav-row {
		display: flex;
		justify-content: space-between;
		margin-bottom: 24px;
	}
	.back-link {
		color: #64748b;
		text-decoration: none;
		font-size: 14px;
	}
	.back-link:hover {
		color: #2563eb;
	}
	.loading,
	.error {
		text-align: center;
		padding: 48px;
		color: #64748b;
	}
	.error {
		color: #dc2626;
	}
	.meta-card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 20px;
		margin-bottom: 24px;
	}
	.meta-row {
		display: flex;
		flex-wrap: wrap;
		gap: 24px;
		margin-bottom: 16px;
	}
	.meta-item {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.meta-label {
		font-size: 11px;
		color: #64748b;
		text-transform: uppercase;
		font-weight: 600;
	}
	.meta-value {
		font-size: 15px;
		font-weight: 500;
		color: #0f172a;
	}
	.mono {
		font-family: monospace;
		font-size: 13px;
	}
	.reanalyze-btn {
		background: #2563eb;
		color: white;
		border: none;
		border-radius: 6px;
		padding: 8px 16px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
	}
	.reanalyze-btn:hover {
		background: #1d4ed8;
	}
	.reanalyze-btn:disabled {
		background: #94a3b8;
		cursor: not-allowed;
	}
	.section {
		margin-bottom: 32px;
	}
	h2 {
		font-size: 18px;
		font-weight: 600;
		color: #0f172a;
		margin-bottom: 16px;
	}
	.insights-grid {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.insight-card {
		border: 1px solid;
		border-radius: 8px;
		padding: 20px;
	}
	.insight-header {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 8px;
	}
	.insight-category {
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.severity-badge {
		font-size: 10px;
		font-weight: 700;
		padding: 1px 5px;
		border-radius: 3px;
	}
	.severity-critical {
		background: #fef2f2;
		color: #dc2626;
	}
	.severity-warning {
		background: #fefce8;
		color: #ca8a04;
	}
	.insight-title {
		font-size: 16px;
		font-weight: 600;
		color: #0f172a;
		margin-bottom: 10px;
	}

	/* Markdown content styling */
	.insight-content {
		font-size: 14px;
		color: #334155;
		line-height: 1.7;
	}
	.insight-content :global(p) {
		margin-bottom: 10px;
	}
	.insight-content :global(p:last-child) {
		margin-bottom: 0;
	}
	.insight-content :global(ul),
	.insight-content :global(ol) {
		margin: 8px 0;
		padding-left: 24px;
	}
	.insight-content :global(li) {
		margin-bottom: 4px;
	}
	.insight-content :global(strong) {
		font-weight: 600;
		color: #0f172a;
	}
	.insight-content :global(code) {
		background: rgba(0, 0, 0, 0.06);
		padding: 1px 5px;
		border-radius: 3px;
		font-size: 13px;
		font-family:
			'SF Mono',
			'Fira Code',
			monospace;
	}
	.insight-content :global(pre) {
		margin: 10px 0;
		padding: 12px 16px;
		background: #f1f5f9;
		border-radius: 6px;
		overflow-x: auto;
		border: 1px solid #e2e8f0;
	}
	.insight-content :global(pre code) {
		background: none;
		padding: 0;
		font-size: 12px;
		line-height: 1.5;
	}
	.insight-content :global(blockquote) {
		margin: 10px 0;
		padding: 8px 16px;
		border-left: 3px solid #cbd5e1;
		color: #64748b;
		background: rgba(0, 0, 0, 0.02);
		border-radius: 0 4px 4px 0;
	}
	.insight-content :global(h4),
	.insight-content :global(h5) {
		font-size: 13px;
		font-weight: 600;
		color: #0f172a;
		margin: 12px 0 6px;
	}
	.insight-content :global(a) {
		color: #2563eb;
		text-decoration: none;
	}
	.insight-content :global(a:hover) {
		text-decoration: underline;
	}

	.context-chart {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 16px;
	}
	.chart-inner {
		position: relative;
		width: 100%;
	}
	.context-svg {
		width: 100%;
		height: auto;
		display: block;
	}
	.axis-text {
		font-size: 10px;
		fill: #94a3b8;
		font-family: inherit;
	}
	.chart-tooltip {
		position: absolute;
		transform: translate(-50%, calc(-100% - 10px));
		background: #0f172a;
		color: white;
		padding: 6px 10px;
		border-radius: 6px;
		font-size: 11px;
		pointer-events: none;
		white-space: nowrap;
		box-shadow: 0 4px 12px rgba(15, 23, 42, 0.18);
		z-index: 2;
	}
	.chart-tooltip.flip-left {
		transform: translate(-8px, calc(-100% - 10px));
	}
	.chart-tooltip.flip-right {
		transform: translate(calc(-100% + 8px), calc(-100% - 10px));
	}
	.tt-turn {
		font-weight: 600;
		margin-bottom: 3px;
	}
	.tt-row {
		display: flex;
		align-items: center;
		gap: 6px;
		color: #cbd5e1;
		line-height: 1.5;
	}
	.tt-dot {
		width: 8px;
		height: 2px;
		border-radius: 1px;
		flex-shrink: 0;
	}
	.tt-dot.prompt {
		background: #6366f1;
	}
	.tt-dot.completion {
		background: #f59e0b;
	}
	.tt-dot.duration {
		background: #10b981;
	}
	.tt-row.slow {
		color: #fca5a5;
		font-size: 10px;
	}

	.collapse-btn {
		background: none;
		border: none;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 0;
		margin-bottom: 12px;
	}
	.collapse-arrow {
		font-size: 10px;
		color: #94a3b8;
		transition: transform 0.15s;
	}
	.collapse-arrow.open {
		transform: rotate(90deg);
	}
	.tool-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.tool-item {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 6px;
		padding: 12px;
	}
	.tool-item.error-tool {
		border-color: #fca5a5;
		background: #fff5f5;
	}
	.tool-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.tool-name {
		font-weight: 600;
		font-size: 13px;
		font-family: monospace;
	}
	.tool-meta {
		font-size: 12px;
		color: #64748b;
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.tool-error {
		color: #dc2626;
		font-weight: 700;
		font-size: 11px;
	}
	.tool-io {
		margin-top: 8px;
	}
	.tool-io summary {
		font-size: 12px;
		color: #64748b;
		cursor: pointer;
	}
	.tool-io pre {
		margin-top: 4px;
		padding: 8px;
		background: #f8fafc;
		border-radius: 4px;
		font-size: 11px;
		overflow-x: auto;
		max-height: 200px;
		overflow-y: auto;
		white-space: pre-wrap;
		word-break: break-all;
	}
	.empty {
		padding: 32px;
		text-align: center;
		color: #64748b;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
	}
</style>
