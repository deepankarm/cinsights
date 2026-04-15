<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { getDigests, getDigest } from '$lib/api';
	import { renderLinkedMarkdown as _renderLinked } from '$lib/markdown';
	import { fmtTokens, fmtMinutes, barPct, maxVal, gradeColor, gradeBg, copyText } from '$lib/format';
	import type { DigestDetail, DigestSectionRead, DigestStatsData } from '$lib/types';

	let digest: DigestDetail | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let showAllSessions = $state(false);
	let expandedCards: Record<string, boolean> = $state({});

	const projectFilter = $derived(page.url.searchParams.get('project'));

	onMount(async () => {
		// Redirect project-scoped reports to the unified project page
		if (projectFilter) {
			void goto(`/projects/${encodeURIComponent(projectFilter)}`, { replaceState: true });
			return;
		}

		try {
			const digests = await getDigests(undefined);
			if (digests.length > 0 && digests[0].status === 'complete') {
				digest = await getDigest(digests[0].id);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load report';
		} finally {
			loading = false;
		}
	});

	function getSection(type: string): DigestSectionRead | undefined {
		return digest?.sections.find((s) => s.section_type === type);
	}

	import type { WeeklyTrend } from '$lib/types';

	let stats: DigestStatsData | null = $derived((digest as DigestDetail | null)?.stats ?? null);

	let sessionIds = $derived(
		(stats?.session_summaries ?? []).map((s: { session_id: string }) => s.session_id) as string[]
	);

	function renderLinkedMarkdown(text: string): string {
		return _renderLinked(text, sessionIds);
	}

	function sparkDelta(trends: WeeklyTrend[], field: keyof WeeklyTrend): { value: string; up: boolean } | null {
		const vals = trends.map(t => t[field]).filter((v): v is number => v != null);
		if (vals.length < 2) return null;
		const d = (vals[vals.length - 1] as number) - (vals[0] as number);
		return { value: (d > 0 ? '+' : '') + d.toFixed(1), up: d > 0 };
	}
	function sparkDeltaPct(trends: WeeklyTrend[], field: keyof WeeklyTrend): { value: string; up: boolean } | null {
		const vals = trends.map(t => t[field]).filter((v): v is number => typeof v === 'number' && v > 0);
		if (vals.length < 2) return null;
		const d = (((vals[vals.length - 1] as number) - (vals[0] as number)) / (vals[0] as number)) * 100;
		return { value: (d > 0 ? '+' : '') + d.toFixed(0) + '%', up: d > 0 };
	}
	function sparkPoints(trends: WeeklyTrend[], field: keyof WeeklyTrend): string {
		const vals = trends.map(t => (t[field] as number) ?? 0);
		const max = Math.max(...vals, 1);
		return vals.map((v, i) => `${i * 20 + 10},${30 - (v / max) * 26}`).join(' ');
	}
	let atAGlance = $derived(getSection('at_a_glance')?.metadata as Record<string, string[]> | undefined);
	let workAreas = $derived(getSection('work_areas')?.metadata as Array<{name: string; session_count: number; description: string}> | undefined);
	let persona = $derived(getSection('developer_persona'));
	let wins = $derived(getSection('impressive_wins')?.metadata as Array<{title: string; description: string; evidence: string}> | undefined);
	let frictions = $derived(getSection('friction_analysis')?.metadata as Array<{category: string; description: string; examples: string[]; severity: string}> | undefined);
	let claudeMd = $derived(getSection('claude_md_suggestions')?.metadata as Array<{rule: string; why: string}> | undefined);
	let features = $derived(getSection('feature_recommendations')?.metadata as Array<{feature: string; title: string; why_for_you: string; setup_code: string | null}> | undefined);
	let patterns = $derived(getSection('workflow_patterns')?.metadata as Array<{name: string; description: string; rationale: string; starter_prompt: string}> | undefined);
	let ambitious = $derived(getSection('ambitious_workflows')?.metadata as Array<{name: string; description: string; rationale: string; starter_prompt: string}> | undefined);
</script>

<svelte:head>
	<title>Insights - cinsights</title>
	<link rel="preconnect" href="https://fonts.googleapis.com">
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">
	<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
	<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css" />
</svelte:head>

{#if loading}
	<div class="loading">
		<div class="loading-dot"></div>
		<div class="loading-dot"></div>
		<div class="loading-dot"></div>
	</div>
{:else if error}
	<div class="error-state">{error}</div>
{:else if !digest}
	<div class="empty-state">
		<div class="empty-icon">
			<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#a1a1aa" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
		</div>
		<h2>No report yet</h2>
		{#if projectFilter}
			<p>Run <code>cinsights digest --days 30 --project {projectFilter}</code> to generate one.</p>
			<a href="/projects" class="back-link">&larr; Back to Projects</a>
		{:else}
			<p>Run <code>cinsights digest --days 30</code> to generate your first report.</p>
		{/if}
	</div>
{:else}

	<!-- Hero -->
	<div class="hero">
		{#if projectFilter}
			<a href="/projects" class="back-link">&larr; All Projects</a>
		{/if}
		<div class="hero-top">
			<div>
				<h1>
					{#if digest.project_name}<span class="project-tag">{digest.project_name}</span>{/if}
					Insights
				</h1>
				<p class="hero-date">
					{new Date(digest.period_start).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} &ndash;
					{new Date(digest.period_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
					{#if digest.sessions_since > 0}
						<span class="staleness-badge">{digest.sessions_since} new session{digest.sessions_since === 1 ? '' : 's'} since</span>
					{/if}
				</p>
			</div>
		</div>

		<!-- Stats strip -->
		{#if stats}
			<div class="stats-strip">
				<div class="ss-item">
					<span class="ss-num ss-indigo">{stats.session_count}</span>
					<span class="ss-label">sessions</span>
				</div>
				{#if stats.analyzed_count < stats.session_count}
					<div class="ss-dot"></div>
					<div class="ss-item">
						<span class="ss-num ss-violet">{stats.analyzed_count}</span>
						<span class="ss-label">analyzed</span>
					</div>
				{/if}
				<div class="ss-dot"></div>
				<div class="ss-item">
					<span class="ss-num ss-violet">{fmtTokens(stats.total_tokens)}</span>
					<span class="ss-label">tokens</span>
				</div>
				<div class="ss-dot"></div>
				<div class="ss-item">
					<span class="ss-num ss-blue">{stats.total_tool_calls.toLocaleString()}</span>
					<span class="ss-label">tool calls</span>
				</div>
				<div class="ss-dot"></div>
				<div class="ss-item">
					<span class="ss-num ss-teal">{fmtMinutes(stats.total_duration_minutes)}</span>
					<span class="ss-label">duration</span>
				</div>
				<div class="ss-dot"></div>
				<div class="ss-item">
					<span class="ss-num ss-emerald">{stats.active_days}</span>
					<span class="ss-label">active days</span>
				</div>
				{#if stats.permission_stats.count > 0}
					<div class="ss-dot"></div>
					<div class="ss-item">
						<span class="ss-num ss-amber">{stats.permission_stats.count}</span>
						<span class="ss-label">permission prompts</span>
					</div>
				{/if}
				{#if !stats.has_claude_md}
					<div class="ss-dot"></div>
					<div class="ss-item">
						<span class="ss-num ss-rose">Missing</span>
						<span class="ss-label">CLAUDE.md</span>
					</div>
				{/if}
			</div>

			<!-- Coverage note -->
			{#if stats.analyzed_count < stats.session_count}
				<div class="coverage-note-bar">
					{stats.analyzed_count} of {stats.session_count} sessions analyzed in depth &middot; Quantitative metrics from all sessions
				</div>
			{/if}

			<!-- Weekly trend sparklines -->
			{#if stats.weekly_trends && stats.weekly_trends.length > 1}
				{@const trends = stats.weekly_trends}
				{@const reDelta = sparkDelta(trends, 'avg_read_edit_ratio')}
				{@const erDelta = sparkDelta(trends, 'avg_error_rate')}
				{@const beDelta = sparkDelta(trends, 'avg_edits_without_read_pct')}
				{@const tkDelta = sparkDeltaPct(trends, 'total_tokens')}
				<div class="trend-sparklines">
					<div class="spark-card">
						<div class="spark-header">
							<span class="spark-label">Read:Edit Ratio</span>
							{#if reDelta}<span class="spark-delta" class:spark-up={reDelta.up} class:spark-down={!reDelta.up}>{reDelta.value}</span>{/if}
						</div>
						<svg class="spark-svg" viewBox="0 0 {trends.length * 20} 32" preserveAspectRatio="none">
							<polyline fill="none" stroke="#6366f1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
								points={sparkPoints(trends, 'avg_read_edit_ratio')} />
						</svg>
						<div class="spark-range"><span>{trends[0].week.slice(5)}</span><span>{trends[trends.length - 1].week.slice(5)}</span></div>
					</div>
					<div class="spark-card">
						<div class="spark-header">
							<span class="spark-label">Error Rate</span>
							{#if erDelta}<span class="spark-delta" class:spark-up={!erDelta.up} class:spark-down={erDelta.up}>{erDelta.value}%</span>{/if}
						</div>
						<svg class="spark-svg" viewBox="0 0 {trends.length * 20} 32" preserveAspectRatio="none">
							<polyline fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
								points={sparkPoints(trends, 'avg_error_rate')} />
						</svg>
						<div class="spark-range"><span>{trends[0].week.slice(5)}</span><span>{trends[trends.length - 1].week.slice(5)}</span></div>
					</div>
					<div class="spark-card">
						<div class="spark-header">
							<span class="spark-label">Blind Edits</span>
							{#if beDelta}<span class="spark-delta" class:spark-up={!beDelta.up} class:spark-down={beDelta.up}>{beDelta.value}%</span>{/if}
						</div>
						<svg class="spark-svg" viewBox="0 0 {trends.length * 20} 32" preserveAspectRatio="none">
							<polyline fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
								points={sparkPoints(trends, 'avg_edits_without_read_pct')} />
						</svg>
						<div class="spark-range"><span>{trends[0].week.slice(5)}</span><span>{trends[trends.length - 1].week.slice(5)}</span></div>
					</div>
					<div class="spark-card">
						<div class="spark-header">
							<span class="spark-label">Tokens/week</span>
							{#if tkDelta}<span class="spark-delta" class:spark-up={tkDelta.up} class:spark-down={!tkDelta.up}>{tkDelta.value}</span>{/if}
						</div>
						<svg class="spark-svg" viewBox="0 0 {trends.length * 20} 32" preserveAspectRatio="none">
							<polyline fill="none" stroke="#0d9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
								points={sparkPoints(trends, 'total_tokens')} />
						</svg>
						<div class="spark-range"><span>{trends[0].week.slice(5)}</span><span>{trends[trends.length - 1].week.slice(5)}</span></div>
					</div>
				</div>
			{/if}
		{/if}
	</div>

	<!-- Permission callout -->
	{#if stats && stats.permission_stats.total_wait_seconds > 30}
		<div class="callout">
			<strong>{(stats.permission_stats.total_wait_seconds / 60).toFixed(1)}min</strong> spent waiting on permission prompts.
			Consider pre-approving common tools.
		</div>
	{/if}

	<!-- At a Glance -->
	{#if atAGlance}
		<section class="sect">
			<div class="glance-grid">
				<div class="glance-card gc-green">
					<div class="gc-icon">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
					</div>
					<h3>What's working</h3>
					<ul>
						{#each atAGlance.whats_working as item}
							<li>{@html renderLinkedMarkdown(item)}</li>
						{/each}
					</ul>
				</div>
				<div class="glance-card gc-amber">
					<div class="gc-icon">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
					</div>
					<h3>What's hindering</h3>
					<ul>
						{#each atAGlance.whats_hindering as item}
							<li>{@html renderLinkedMarkdown(item)}</li>
						{/each}
					</ul>
				</div>
				<div class="glance-card gc-blue">
					<div class="gc-icon">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
					</div>
					<h3>Quick wins</h3>
					<ul>
						{#each atAGlance.quick_wins as item}
							<li>{@html renderLinkedMarkdown(item)}</li>
						{/each}
					</ul>
				</div>
				<div class="glance-card gc-violet">
					<div class="gc-icon">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
					</div>
					<h3>Ambitious ideas</h3>
					<ul>
						{#each atAGlance.ambitious_workflows as item}
							<li>{@html renderLinkedMarkdown(item)}</li>
						{/each}
					</ul>
				</div>
			</div>
		</section>
	{/if}

	<!-- Charts — bento style -->
	{#if stats}
		<section class="sect">
			<h2 class="sect-title">Activity</h2>
			<div class="chart-bento">
				<div class="chart-box chart-wide">
					<h3>Tools</h3>
					<div class="hbars">
						{#each Object.entries(stats.tool_distribution).slice(0, 8) as [name, count]}
							{@const pct = barPct(count, maxVal(stats.tool_distribution))}
							<div class="hbar">
								<span class="hbar-name">{name}</span>
								<div class="hbar-track">
									<div class="hbar-fill hbar-c1" style="width:{pct}%"></div>
								</div>
								<span class="hbar-val">{count}</span>
							</div>
						{/each}
					</div>
				</div>
				<div class="chart-box">
					<h3>Languages</h3>
					<div class="hbars">
						{#each Object.entries(stats.language_distribution).slice(0, 6) as [lang, count]}
							{@const pct = barPct(count, maxVal(stats.language_distribution))}
							<div class="hbar">
								<span class="hbar-name">{lang}</span>
								<div class="hbar-track">
									<div class="hbar-fill hbar-c2" style="width:{pct}%"></div>
								</div>
								<span class="hbar-val">{count}</span>
							</div>
						{/each}
						{#if Object.keys(stats.language_distribution).length === 0}
							<span class="chart-empty">No data</span>
						{/if}
					</div>
				</div>
				<div class="chart-box">
					<h3>Coding hours</h3>
					<div class="hour-bars">
						{#each Object.entries(stats.time_of_day) as [hour, count]}
							{@const pct = barPct(count, maxVal(stats.time_of_day))}
							<div class="hour-col" title="{hour}:00 — {count} sessions">
								<div class="hour-fill" style="height:{pct}%"></div>
								<span class="hour-label">{hour}</span>
							</div>
						{/each}
					</div>
				</div>
				<div class="chart-box">
					<h3>Errors</h3>
					<div class="hbars">
						{#each Object.entries(stats.error_types).slice(0, 5) as [type, count]}
							{@const pct = barPct(count, maxVal(stats.error_types))}
							<div class="hbar">
								<span class="hbar-name">{type}</span>
								<div class="hbar-track">
									<div class="hbar-fill hbar-c4" style="width:{pct}%"></div>
								</div>
								<span class="hbar-val">{count}</span>
							</div>
						{/each}
						{#if Object.keys(stats.error_types).length === 0}
							<span class="chart-empty">No errors</span>
						{/if}
					</div>
				</div>
				<div class="chart-box chart-wide">
					<h3>Tokens by session</h3>
					<div class="hbars">
						{#each stats.tokens_per_session as t}
							{@const sessionNum = sessionIds.indexOf(t.session_id) + 1}
							<a href="/sessions/{t.session_id}" class="hbar hbar-link">
								<span class="hbar-name">{sessionNum > 0 ? `Session ${sessionNum}` : t.session_id.slice(0, 8)}</span>
								<div class="hbar-track">
									<div class="hbar-fill hbar-c1" style="width:{barPct(t.tokens, Math.max(...stats.tokens_per_session.map(x => x.tokens), 1))}%"></div>
								</div>
								<span class="hbar-val">{fmtTokens(t.tokens)}</span>
							</a>
						{/each}
					</div>
				</div>
			</div>
		</section>

		<!-- Session Health -->
		{@const healthLimit = 20}
		{@const healthItems = showAllSessions ? stats.session_health : stats.session_health.slice(0, healthLimit)}
		<section class="sect">
			<h2 class="sect-title">Session health <span class="count-badge">{stats.session_health.length}</span></h2>
			<div class="health-grid">
				{#each healthItems as h}
					{@const sessionNum = sessionIds.indexOf(h.session_id) + 1}
					<a href="/sessions/{h.session_id}" class="health-pill" style="background:{gradeBg(h.grade)}">
						<span class="health-grade" style="color:{gradeColor(h.grade)}">{h.grade}</span>
						<div class="health-info">
							{#if sessionNum > 0}<span class="health-name">Session {sessionNum}</span>{/if}
							<span class="health-meta">{h.duration_minutes}m &middot; {h.tool_count} tools &middot; {fmtTokens(h.total_tokens ?? 0)}</span>
						</div>
					</a>
				{/each}
			</div>
			{#if stats.session_health.length > healthLimit}
				<button class="show-more" onclick={() => showAllSessions = !showAllSessions}>
					{showAllSessions ? 'Show fewer' : `Show all ${stats.session_health.length}`}
				</button>
			{/if}
		</section>
	{/if}

	<!-- Work Areas + Persona side by side -->
	{#if (workAreas && workAreas.length > 0) || persona}
		<section class="sect">
			<div class="duo-grid">
				{#if workAreas && workAreas.length > 0}
					<div>
						<h2 class="sect-title">Work areas</h2>
						<div class="stack-sm">
							{#each workAreas as area}
								<div class="content-card">
									<div class="content-card-head">
										<strong>{area.name}</strong>
										<span class="pill-sm">{area.session_count} sessions</span>
									</div>
									<p>{@html renderLinkedMarkdown(area.description)}</p>
								</div>
							{/each}
						</div>
					</div>
				{/if}
				{#if persona}
					<div>
						<h2 class="sect-title">How you use coding agents</h2>
						<div class="persona markdown-body">
							{@html renderLinkedMarkdown(persona.content)}
						</div>
					</div>
				{/if}
			</div>
		</section>
	{/if}

	<!-- Wins -->
	{#if wins && wins.length > 0}
		<section class="sect">
			<h2 class="sect-title">Wins</h2>
			<div class="stack">
				{#each wins as win}
					<div class="accent-card accent-green">
						<h3>{win.title}</h3>
						<p>{@html renderLinkedMarkdown(win.description)}</p>
						<div class="accent-card-sub">{@html renderLinkedMarkdown(win.evidence)}</div>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Friction -->
	{#if frictions && frictions.length > 0}
		<section class="sect">
			<h2 class="sect-title">Friction</h2>
			<div class="stack">
				{#each frictions as f}
					<div class="accent-card accent-red">
						<div class="accent-card-head">
							<h3>{f.category}</h3>
							{#if f.severity === 'critical'}
								<span class="tag tag-red">Critical</span>
							{:else if f.severity === 'warning'}
								<span class="tag tag-amber">Warning</span>
							{/if}
						</div>
						<p>{@html renderLinkedMarkdown(f.description)}</p>
						{#if f.examples && f.examples.length > 0}
							<ul class="examples">
								{#each f.examples as ex}
									<li>{@html renderLinkedMarkdown(ex)}</li>
								{/each}
							</ul>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- CLAUDE.md Suggestions -->
	{#if claudeMd && claudeMd.length > 0}
		<section class="sect">
			<h2 class="sect-title">CLAUDE.md suggestions</h2>
			<p class="sect-sub">Copy these rules into your CLAUDE.md.</p>
			<div class="stack">
				{#each claudeMd as suggestion}
					<div class="rule-card">
						<div class="rule-top">
							<pre class="rule-code">{suggestion.rule}</pre>
							<button class="btn-copy" onclick={(e) => copyText(suggestion.rule, e.currentTarget as HTMLButtonElement)}>Copy</button>
						</div>
						<p class="rule-why">{@html renderLinkedMarkdown(suggestion.why)}</p>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Features -->
	{#if features && features.length > 0}
		<section class="sect">
			<h2 class="sect-title">Features to try</h2>
			<div class="stack">
				{#each features as feat, i}
					<div class="expand-card" class:expanded={expandedCards[`feat-${i}`]}>
						<button class="expand-head" onclick={() => expandedCards[`feat-${i}`] = !expandedCards[`feat-${i}`]}>
							<div>
								<span class="expand-tag">{feat.feature}</span>
								<h3>{feat.title}</h3>
							</div>
							<span class="expand-chevron">{expandedCards[`feat-${i}`] ? '−' : '+'}</span>
						</button>
						{#if expandedCards[`feat-${i}`]}
							<div class="expand-body">
								<p>{@html renderLinkedMarkdown(feat.why_for_you)}</p>
								{#if feat.setup_code}
									<div class="code-wrap">
										<pre>{feat.setup_code}</pre>
										<button class="btn-copy" onclick={(e) => copyText(feat.setup_code ?? '', e.currentTarget as HTMLButtonElement)}>Copy</button>
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Patterns -->
	{#if patterns && patterns.length > 0}
		<section class="sect">
			<h2 class="sect-title">Workflow patterns</h2>
			<div class="stack">
				{#each patterns as p, i}
					<div class="expand-card" class:expanded={expandedCards[`pat-${i}`]}>
						<button class="expand-head" onclick={() => expandedCards[`pat-${i}`] = !expandedCards[`pat-${i}`]}>
							<div><h3>{p.name}</h3></div>
							<span class="expand-chevron">{expandedCards[`pat-${i}`] ? '−' : '+'}</span>
						</button>
						{#if expandedCards[`pat-${i}`]}
							<div class="expand-body">
								<p>{@html renderLinkedMarkdown(p.description)}</p>
								<p class="muted">{@html renderLinkedMarkdown(p.rationale)}</p>
								<div class="code-wrap">
									<span class="code-label">Starter prompt</span>
									<pre>{p.starter_prompt}</pre>
									<button class="btn-copy" onclick={(e) => copyText(p.starter_prompt, e.currentTarget as HTMLButtonElement)}>Copy</button>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Ambitious -->
	{#if ambitious && ambitious.length > 0}
		<section class="sect">
			<h2 class="sect-title">On the horizon</h2>
			<div class="stack">
				{#each ambitious as a, i}
					<div class="expand-card" class:expanded={expandedCards[`amb-${i}`]}>
						<button class="expand-head" onclick={() => expandedCards[`amb-${i}`] = !expandedCards[`amb-${i}`]}>
							<div><h3>{a.name}</h3></div>
							<span class="expand-chevron">{expandedCards[`amb-${i}`] ? '−' : '+'}</span>
						</button>
						{#if expandedCards[`amb-${i}`]}
							<div class="expand-body">
								<p>{@html renderLinkedMarkdown(a.description)}</p>
								<p class="muted">{@html renderLinkedMarkdown(a.rationale)}</p>
								<div class="code-wrap">
									<span class="code-label">Starter prompt</span>
									<pre>{a.starter_prompt}</pre>
									<button class="btn-copy" onclick={(e) => copyText(a.starter_prompt, e.currentTarget as HTMLButtonElement)}>Copy</button>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<footer class="report-footer">
		Generated {new Date(digest.created_at).toLocaleString()} &middot;
		{(digest.analysis_prompt_tokens + digest.analysis_completion_tokens).toLocaleString()} tokens
	</footer>
{/if}

<style>
	/* ── States ── */
	.loading { display: flex; justify-content: center; gap: 6px; padding: 80px; }
	.loading-dot { width: 8px; height: 8px; border-radius: 50%; background: #a1a1aa; animation: pulse 1.2s ease-in-out infinite; }
	.loading-dot:nth-child(2) { animation-delay: 0.15s; }
	.loading-dot:nth-child(3) { animation-delay: 0.3s; }
	@keyframes pulse { 0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); } 40% { opacity: 1; transform: scale(1); } }

	.error-state { text-align: center; padding: 80px; color: #ef4444; }
	.empty-state { text-align: center; padding: 100px 24px; }
	.empty-icon { margin-bottom: 20px; }
	.empty-state h2 { font-size: 20px; font-weight: 600; color: #232326; margin-bottom: 8px; }
	.empty-state p { color: #70707a; font-size: 14px; }
	.empty-state code { background: #f0f0f2; padding: 2px 8px; border-radius: 5px; font-size: 13px; }

	.back-link { color: #70707a; text-decoration: none; font-size: 13px; display: inline-block; margin-bottom: 8px; }
	.back-link:hover { color: #232326; }

	/* ── Hero ── */
	.hero { margin-bottom: 36px; }
	.hero-top { margin-bottom: 24px; }
	.hero h1 {
		font-size: 30px;
		font-weight: 800;
		color: #232326;
		letter-spacing: -0.8px;
		line-height: 1.2;
	}
	.project-tag {
		display: inline-block;
		font-size: 13px;
		font-weight: 600;
		color: white;
		background: linear-gradient(135deg, #7c3aed, #6366f1);
		padding: 3px 12px;
		border-radius: 6px;
		vertical-align: middle;
		margin-right: 8px;
		letter-spacing: 0;
	}
	.hero-date { color: #a1a1aa; font-size: 14px; margin-top: 6px; }
	.staleness-badge { display: inline-block; font-size: 11px; font-weight: 600; color: #b45309; background: #fef3c7; border: 1px solid #fcd34d; padding: 2px 8px; border-radius: 4px; margin-left: 8px; vertical-align: middle; }

	/* ── Stats strip ── */
	.stats-strip {
		display: flex;
		align-items: center;
		gap: 20px;
		background: white;
		border-radius: 14px;
		padding: 16px 28px;
		flex-wrap: wrap;
	}
	.ss-item { display: flex; align-items: baseline; gap: 6px; }
	.ss-num {
		font-size: 20px;
		font-weight: 800;
		letter-spacing: -0.5px;
		font-variant-numeric: tabular-nums;
	}
	.ss-label { font-size: 12px; color: #a1a1aa; font-weight: 500; }
	.ss-dot { width: 3px; height: 3px; border-radius: 50%; background: #d4d4d8; flex-shrink: 0; }
	.ss-indigo { color: #6366f1; }
	.ss-violet { color: #8b5cf6; }
	.ss-blue { color: #3b82f6; }
	.ss-teal { color: #0d9488; }
	.ss-emerald { color: #10b981; }
	.ss-amber { color: #d97706; }
	.ss-rose { color: #ef4444; font-size: 14px; }

	/* ── Coverage note ── */
	.coverage-note-bar {
		margin-top: 10px;
		font-size: 12px;
		color: #71717a;
		text-align: center;
	}

	/* ── Trend sparklines ── */
	.trend-sparklines {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 10px;
		margin-top: 14px;
	}
	.spark-card {
		background: white;
		border-radius: 12px;
		padding: 14px 16px 10px;
	}
	.spark-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
	.spark-label { font-size: 11px; font-weight: 600; color: #71717a; text-transform: uppercase; letter-spacing: 0.04em; }
	.spark-delta { font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }
	.spark-up { color: #10b981; }
	.spark-down { color: #ef4444; }
	.spark-svg { width: 100%; height: 32px; }
	.spark-range { display: flex; justify-content: space-between; font-size: 9px; color: #a1a1aa; margin-top: 4px; }

	/* ── Callout ── */
	.callout {
		background: linear-gradient(135deg, #fffbeb, #fef3c7);
		border-radius: 12px;
		padding: 14px 20px;
		font-size: 14px;
		color: #92400e;
		margin-bottom: 40px;
	}

	/* ── Sections ── */
	.sect { margin-bottom: 48px; }
	.sect-title { font-size: 20px; font-weight: 700; color: #232326; margin-bottom: 18px; letter-spacing: -0.3px; }
	.sect-sub { font-size: 14px; color: #70707a; margin: -10px 0 16px; }

	.count-badge {
		font-size: 13px;
		font-weight: 600;
		color: #6366f1;
		background: #eef2ff;
		padding: 2px 10px;
		border-radius: 100px;
		vertical-align: middle;
		margin-left: 4px;
	}

	.stack { display: flex; flex-direction: column; gap: 12px; }
	.stack-sm { display: flex; flex-direction: column; gap: 10px; }

	/* ── At a Glance ── */
	.glance-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 14px;
	}
	.glance-card {
		border-radius: 16px;
		padding: 22px 24px;
	}
	.gc-icon {
		width: 32px;
		height: 32px;
		border-radius: 10px;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-bottom: 12px;
	}
	.glance-card h3 {
		font-size: 13px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 10px;
	}
	.glance-card ul { padding-left: 18px; font-size: 14px; line-height: 1.7; }
	.glance-card ul li { margin-bottom: 4px; }
	.glance-card ul li :global(p) { display: inline; }

	.gc-green { background: linear-gradient(135deg, #ecfdf5, #d1fae5); }
	.gc-green .gc-icon { background: #10b981; color: white; }
	.gc-green h3 { color: #047857; }
	.gc-green ul { color: #065f46; }

	.gc-amber { background: linear-gradient(135deg, #fffbeb, #fef3c7); }
	.gc-amber .gc-icon { background: #f59e0b; color: white; }
	.gc-amber h3 { color: #b45309; }
	.gc-amber ul { color: #78350f; }

	.gc-blue { background: linear-gradient(135deg, #eff6ff, #dbeafe); }
	.gc-blue .gc-icon { background: #3b82f6; color: white; }
	.gc-blue h3 { color: #1d4ed8; }
	.gc-blue ul { color: #1e3a5f; }

	.gc-violet { background: linear-gradient(135deg, #f5f3ff, #ede9fe); }
	.gc-violet .gc-icon { background: #8b5cf6; color: white; }
	.gc-violet h3 { color: #6d28d9; }
	.gc-violet ul { color: #4c1d95; }

	/* ── Charts ── */
	.chart-bento {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 14px;
	}
	.chart-box {
		background: white;
		border-radius: 16px;
		padding: 22px 24px;
	}
	.chart-wide { grid-column: span 2; }
	.chart-box h3 {
		font-size: 13px;
		font-weight: 700;
		color: #232326;
		margin-bottom: 16px;
	}
	.chart-empty { color: #a1a1aa; font-size: 13px; }

	/* Horizontal bars */
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
	.hbar-link { text-decoration: none; border-radius: 8px; padding: 2px 0; transition: background 0.15s; }
	.hbar-link:hover { background: #f9fafb; }

	/* Vertical time bars */
	.hour-bars { display: flex; align-items: flex-end; gap: 4px; height: 120px; padding-top: 8px; }
	.hour-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
	.hour-fill {
		width: 100%;
		border-radius: 4px 4px 0 0;
		background: linear-gradient(180deg, #8b5cf6, #ddd6fe);
		transition: height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
		min-height: 2px;
	}
	.hour-label { font-size: 10px; color: #a1a1aa; margin-top: 4px; }

	/* ── Health ── */
	.health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
	.health-pill {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 16px;
		border-radius: 12px;
		text-decoration: none;
		color: inherit;
		transition: transform 0.15s, box-shadow 0.15s;
	}
	.health-pill:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
	.health-grade { font-size: 22px; font-weight: 800; flex-shrink: 0; }
	.health-info { display: flex; flex-direction: column; min-width: 0; }
	.health-name { font-size: 13px; font-weight: 600; color: #232326; }
	.health-meta { font-size: 12px; color: #a1a1aa; }
	.show-more {
		display: block;
		margin: 16px auto 0;
		background: white;
		border: none;
		border-radius: 10px;
		padding: 10px 24px;
		font-size: 13px;
		font-weight: 500;
		color: #70707a;
		cursor: pointer;
		transition: all 0.15s;
	}
	.show-more:hover { color: #232326; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }

	/* ── Duo grid (work areas + persona) ── */
	.duo-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }

	.content-card {
		background: white;
		border-radius: 14px;
		padding: 18px 20px;
	}
	.content-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
	.content-card-head strong { font-size: 15px; color: #232326; }
	.content-card p { font-size: 14px; color: #52525b; line-height: 1.6; }

	.pill-sm {
		font-size: 12px;
		color: #6366f1;
		background: #eef2ff;
		padding: 2px 10px;
		border-radius: 100px;
		white-space: nowrap;
		font-weight: 500;
	}

	.persona {
		background: white;
		border-radius: 14px;
		padding: 24px;
		font-size: 14px;
		color: #52525b;
		line-height: 1.8;
	}
	.persona :global(p) { margin-bottom: 14px; }
	.persona :global(strong) { color: #232326; }

	/* ── Accent cards ── */
	.accent-card {
		background: white;
		border-radius: 14px;
		padding: 20px 22px;
		border-left: 4px solid;
	}
	.accent-card h3 { font-size: 15px; font-weight: 600; color: #232326; margin-bottom: 6px; }
	.accent-card p { font-size: 14px; color: #52525b; line-height: 1.65; margin-bottom: 6px; }
	.accent-card-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
	.accent-card-sub { font-size: 13px; color: #70707a; }
	.accent-green { border-left-color: #10b981; background: linear-gradient(90deg, #f0fdf4, white 40%); }
	.accent-red { border-left-color: #ef4444; background: linear-gradient(90deg, #fef2f2, white 40%); }

	.tag { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 100px; }
	.tag-red { background: #fef2f2; color: #ef4444; }
	.tag-amber { background: #fffbeb; color: #d97706; }

	.examples { margin: 8px 0 0 20px; font-size: 13px; color: #52525b; line-height: 1.6; }
	.examples li { margin-bottom: 4px; }

	/* ── Rule cards (CLAUDE.md) ── */
	.rule-card {
		background: linear-gradient(135deg, #eef2ff, #e0e7ff);
		border-radius: 14px;
		padding: 20px 22px;
	}
	.rule-top { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; }
	.rule-code {
		flex: 1;
		background: white;
		border: 1px solid #c7d2fe;
		border-radius: 8px;
		padding: 12px 14px;
		font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
		font-size: 13px;
		color: #312e81;
		white-space: pre-wrap;
		word-break: break-word;
		margin: 0;
	}
	.rule-why { font-size: 13px; color: #4338ca; line-height: 1.55; }

	/* ── Expandable cards ── */
	.expand-card { background: white; border-radius: 14px; overflow: hidden; transition: box-shadow 0.15s; }
	.expand-card:hover { box-shadow: 0 2px 12px rgba(99, 102, 241, 0.08); }
	.expand-head {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		padding: 18px 22px;
		cursor: pointer;
		background: none;
		border: none;
		width: 100%;
		text-align: left;
		font: inherit;
		color: inherit;
	}
	.expand-head h3 { font-size: 15px; font-weight: 600; color: #232326; margin: 0; }
	.expand-tag { display: block; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #6366f1; margin-bottom: 4px; }
	.expand-chevron { font-size: 20px; color: #a1a1aa; line-height: 1; flex-shrink: 0; }
	.expand-body { padding: 0 22px 20px; }
	.expand-body p { font-size: 14px; color: #52525b; line-height: 1.65; margin-bottom: 8px; }
	.muted { color: #70707a !important; font-size: 13px !important; }
	.expanded { box-shadow: 0 0 0 1.5px #6366f1, 0 2px 12px rgba(99, 102, 241, 0.1) !important; }

	/* ── Code blocks ── */
	.code-wrap { margin-top: 10px; position: relative; }
	.code-wrap pre {
		background: #fafafa;
		border: 1px solid #e4e4e7;
		border-radius: 10px;
		padding: 14px 16px;
		font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
		font-size: 12px;
		color: #232326;
		white-space: pre-wrap;
		word-break: break-word;
		margin: 0;
	}
	.code-label { display: block; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #a1a1aa; margin-bottom: 6px; }

	.btn-copy {
		background: #eef2ff;
		border: none;
		border-radius: 8px;
		padding: 6px 14px;
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		color: #6366f1;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.btn-copy:hover { background: #e0e7ff; color: #4f46e5; }

	/* ── Markdown globals ── */
	.accent-card :global(a), .persona :global(a), .glance-card :global(a), .content-card :global(a) {
		color: #6366f1;
		text-decoration: none;
	}
	.accent-card :global(a:hover), .persona :global(a:hover), .glance-card :global(a:hover), .content-card :global(a:hover) {
		text-decoration: underline;
	}
	.accent-card :global(code), .persona :global(code), .content-card :global(code) {
		background: #f4f4f5;
		padding: 1px 6px;
		border-radius: 4px;
		font-size: 0.9em;
	}

	/* ── Footer ── */
	.report-footer { text-align: center; padding: 32px; color: #a1a1aa; font-size: 12px; }

	/* ── Responsive ── */
	@media (max-width: 768px) {
		.stats-strip { gap: 12px; padding: 14px 20px; }
		.ss-num { font-size: 16px; }
		.chart-bento { grid-template-columns: 1fr; }
		.chart-wide { grid-column: span 1; }
		.glance-grid { grid-template-columns: 1fr; }
		.duo-grid { grid-template-columns: 1fr; }
		.trend-sparklines { grid-template-columns: repeat(2, 1fr); }
	}
</style>
