<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getDigests, getDigest } from '$lib/api';
	import { renderMarkdown } from '$lib/markdown';
	import type { DigestDetail, DigestSectionRead, DigestStatsData } from '$lib/types';

	let digest: DigestDetail | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let showAllSessions = $state(false);

	const projectFilter = $derived(page.url.searchParams.get('project'));

	onMount(async () => {
		try {
			const digests = await getDigests(projectFilter ?? undefined);
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

	// Map "Session 1", "Session 3" etc. to clickable links using session_summaries order
	let sessionIds = $derived(
		(stats?.session_summaries ?? []).map((s: { session_id: string }) => s.session_id) as string[]
	);

	function linkifySessions(text: string): string {
		if (!sessionIds.length) return text;
		return text.replace(/Session (\d+)('s)?/gi, (match, num, possessive) => {
			const idx = parseInt(num) - 1;
			if (idx >= 0 && idx < sessionIds.length) {
				return `[${match}](/sessions/${sessionIds[idx]})`;
			}
			return match;
		});
	}

	function renderLinkedMarkdown(text: string): string {
		return renderMarkdown(linkifySessions(text));
	}

	function formatTokens(n: number): string {
		if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
		if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
		return n.toString();
	}

	function barWidth(value: number, max: number): string {
		return `${Math.max(2, (value / max) * 100)}%`;
	}

	function maxVal(obj: Record<string, number>): number {
		return Math.max(...Object.values(obj), 1);
	}

	function gradeColor(grade: string): string {
		switch (grade) {
			case 'A': return '#16a34a';
			case 'B': return '#65a30d';
			case 'C': return '#eab308';
			case 'D': return '#f97316';
			case 'F': return '#dc2626';
			default: return '#64748b';
		}
	}

	function copyText(text: string, btn: HTMLButtonElement) {
		navigator.clipboard.writeText(text).then(() => {
			const orig = btn.textContent;
			btn.textContent = 'Copied!';
			setTimeout(() => { btn.textContent = orig; }, 2000);
		});
	}

	let stats = $derived(digest?.stats as DigestStatsData | null);
	let atAGlance = $derived(getSection('at_a_glance')?.metadata as Record<string, string> | undefined);
	let workAreas = $derived(getSection('work_areas')?.metadata as Array<{name: string; session_count: number; description: string}> | undefined);
	let persona = $derived(getSection('developer_persona'));
	let wins = $derived(getSection('impressive_wins')?.metadata as Array<{title: string; description: string; evidence: string}> | undefined);
	let frictions = $derived(getSection('friction_analysis')?.metadata as Array<{category: string; description: string; examples: string[]; severity: string}> | undefined);
	let claudeMd = $derived(getSection('claude_md_suggestions')?.metadata as Array<{rule: string; why: string}> | undefined);
	let features = $derived(getSection('feature_recommendations')?.metadata as Array<{feature: string; title: string; why_for_you: string; setup_code: string | null}> | undefined);
	let patterns = $derived(getSection('workflow_patterns')?.metadata as Array<{name: string; description: string; rationale: string; starter_prompt: string}> | undefined);
	let ambitious = $derived(getSection('ambitious_workflows')?.metadata as Array<{name: string; description: string; rationale: string; starter_prompt: string}> | undefined);
	// fun_ending removed — users found it annoying
</script>

<svelte:head>
	<title>Insights Report - cinsights</title>
	<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css" />
</svelte:head>

{#if loading}
	<div class="loading">Loading report...</div>
{:else if error}
	<div class="error">{error}</div>
{:else if !digest}
	<div class="empty-state">
		<h2>No Report Yet</h2>
		{#if projectFilter}
			<p>Run <code>cinsights digest --days 30 --project {projectFilter}</code> to generate a report for this project.</p>
			<a href="/projects" class="back-link">&larr; Back to Projects</a>
		{:else}
			<p>Run <code>cinsights digest --days 30</code> to generate your insights report.</p>
		{/if}
	</div>
{:else}
	<!-- Header -->
	<div class="report-header">
		{#if projectFilter}
			<a href="/projects" class="back-link">&larr; All Projects</a>
		{/if}
		<h1>
			{#if digest.project_name}
				<span class="project-label">{digest.project_name}</span>
			{/if}
			Insights Report
		</h1>
		<p class="subtitle">
			{new Date(digest.period_start).toLocaleDateString()} - {new Date(digest.period_end).toLocaleDateString()}
			| {digest.session_count} sessions
		</p>
	</div>

	<!-- At a Glance -->
	{#if atAGlance}
		<div class="glance-banner">
			<h2 class="glance-title">At a Glance</h2>
			<div class="glance-grid">
				<div class="glance-item glance-working">
					<strong>What's working:</strong> {@html renderLinkedMarkdown(atAGlance.whats_working)}
				</div>
				<div class="glance-item glance-hindering">
					<strong>What's hindering:</strong> {@html renderLinkedMarkdown(atAGlance.whats_hindering)}
				</div>
				<div class="glance-item glance-wins">
					<strong>Quick wins:</strong> {@html renderLinkedMarkdown(atAGlance.quick_wins)}
				</div>
				<div class="glance-item glance-ambitious">
					<strong>Ambitious workflows:</strong> {@html renderLinkedMarkdown(atAGlance.ambitious_workflows)}
				</div>
			</div>
		</div>
	{/if}

	<!-- Stats Pills -->
	{#if stats}
		<div class="stats-pills">
			<div class="pill"><span class="pill-value">{stats.session_count}</span><span class="pill-label">Sessions</span></div>
			<div class="pill"><span class="pill-value">{formatTokens(stats.total_tokens)}</span><span class="pill-label">Tokens</span></div>
			<div class="pill"><span class="pill-value">{stats.total_tool_calls}</span><span class="pill-label">Tool Calls</span></div>
			<div class="pill"><span class="pill-value">{stats.total_duration_minutes.toFixed(0)}m</span><span class="pill-label">Duration</span></div>
			<div class="pill"><span class="pill-value">{stats.active_days}</span><span class="pill-label">Active Days</span></div>
			<div class="pill"><span class="pill-value">{stats.plan_mode_stats.entries}</span><span class="pill-label">Plan Mode</span></div>
			{#if stats.permission_stats.count > 0}
				<div class="pill pill-warn"><span class="pill-value">{stats.permission_stats.count}</span><span class="pill-label">Permission Prompts</span></div>
			{/if}
			{#if !stats.has_claude_md}
				<div class="pill pill-alert"><span class="pill-value">Missing</span><span class="pill-label">CLAUDE.md</span></div>
			{/if}
		</div>

		<!-- Permission wait time callout -->
		{#if stats.permission_stats.total_wait_seconds > 30}
			<div class="callout callout-warn">
				You spent <strong>{(stats.permission_stats.total_wait_seconds / 60).toFixed(1)} minutes</strong> waiting on permission prompts
				({stats.permission_stats.count} prompts, avg {stats.permission_stats.avg_wait_seconds.toFixed(0)}s, max {stats.permission_stats.max_wait_seconds.toFixed(0)}s).
				Consider pre-approving common tools in your settings.
			</div>
		{/if}

		<!-- Charts Row 1: Tools + Errors -->
		<div class="charts-row">
			<div class="chart-card">
				<div class="chart-title">Tool Distribution</div>
				{#each Object.entries(stats.tool_distribution).slice(0, 8) as [name, count]}
					<div class="bar-row">
						<span class="bar-label">{name}</span>
						<div class="bar-track"><div class="bar-fill bar-blue" style="width:{barWidth(count, maxVal(stats.tool_distribution))}"></div></div>
						<span class="bar-value">{count}</span>
					</div>
				{/each}
			</div>
			<div class="chart-card">
				<div class="chart-title">Languages</div>
				{#each Object.entries(stats.language_distribution).slice(0, 8) as [lang, count]}
					<div class="bar-row">
						<span class="bar-label">{lang}</span>
						<div class="bar-track"><div class="bar-fill bar-green" style="width:{barWidth(count, maxVal(stats.language_distribution))}"></div></div>
						<span class="bar-value">{count}</span>
					</div>
				{/each}
				{#if Object.keys(stats.language_distribution).length === 0}
					<div class="bar-empty">No language data</div>
				{/if}
			</div>
		</div>

		<!-- Charts Row 2: Time of Day + Errors -->
		<div class="charts-row">
			<div class="chart-card">
				<div class="chart-title">Time of Day</div>
				{#each Object.entries(stats.time_of_day) as [hour, count]}
					<div class="bar-row">
						<span class="bar-label">{hour}:00</span>
						<div class="bar-track"><div class="bar-fill bar-purple" style="width:{barWidth(count, maxVal(stats.time_of_day))}"></div></div>
						<span class="bar-value">{count}</span>
					</div>
				{/each}
			</div>
			<div class="chart-card">
				<div class="chart-title">Error Types</div>
				{#each Object.entries(stats.error_types).slice(0, 6) as [type, count]}
					<div class="bar-row">
						<span class="bar-label">{type}</span>
						<div class="bar-track"><div class="bar-fill bar-red" style="width:{barWidth(count, maxVal(stats.error_types))}"></div></div>
						<span class="bar-value">{count}</span>
					</div>
				{/each}
				{#if Object.keys(stats.error_types).length === 0}
					<div class="bar-empty">No errors recorded</div>
				{/if}
			</div>
		</div>

		<!-- Session Health Grid -->
		{@const healthLimit = 20}
		{@const healthItems = showAllSessions ? stats.session_health : stats.session_health.slice(0, healthLimit)}
		<div class="section">
			<h2>Session Health ({stats.session_health.length})</h2>
			<div class="health-grid">
				{#each healthItems as h}
					{@const sessionNum = sessionIds.indexOf(h.session_id) + 1}
					<a href="/sessions/{h.session_id}" class="health-card" style="border-left: 3px solid {gradeColor(h.grade)}">
						<div class="health-top">
							<span class="health-grade" style="color:{gradeColor(h.grade)}">{h.grade}</span>
							{#if sessionNum > 0}
								<span class="health-session-num">Session {sessionNum}</span>
							{/if}
						</div>
						<span class="health-date">{new Date(h.start_time).toLocaleDateString()}</span>
						<span class="health-meta">{h.duration_minutes}m | {h.tool_count} tools | {formatTokens(h.total_tokens ?? 0)}</span>
					</a>
				{/each}
			</div>
			{#if stats.session_health.length > healthLimit}
				<button class="show-more-btn" onclick={() => showAllSessions = !showAllSessions}>
					{showAllSessions ? 'Show fewer' : `Show all ${stats.session_health.length} sessions`}
				</button>
			{/if}
		</div>
	{/if}

	<!-- Work Areas -->
	{#if workAreas && workAreas.length > 0}
		<div class="section">
			<h2>What You Work On</h2>
			<div class="work-areas">
				{#each workAreas as area}
					<div class="work-area-card">
						<div class="work-area-header">
							<span class="work-area-name">{area.name}</span>
							<span class="work-area-count">~{area.session_count} sessions</span>
						</div>
						<p class="work-area-desc">{@html renderLinkedMarkdown(area.description)}</p>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Developer Persona -->
	{#if persona}
		<div class="section">
			<h2>How You Use Claude Code</h2>
			<div class="persona-card markdown-body">
				{@html renderLinkedMarkdown(persona.content)}
			</div>
		</div>
	{/if}

	<!-- Impressive Wins -->
	{#if wins && wins.length > 0}
		<div class="section">
			<h2>Impressive Things You Did</h2>
			<div class="cards-list">
				{#each wins as win}
					<div class="card card-green">
						<h3>{win.title}</h3>
						<p>{@html renderLinkedMarkdown(win.description)}</p>
						<div class="card-evidence">{@html renderLinkedMarkdown(win.evidence)}</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Friction Analysis -->
	{#if frictions && frictions.length > 0}
		<div class="section">
			<h2>Where Things Go Wrong</h2>
			<div class="cards-list">
				{#each frictions as f}
					<div class="card card-red">
						<div class="card-header">
							<h3>{f.category}</h3>
							{#if f.severity === 'critical'}
								<span class="severity-badge severity-critical">!!</span>
							{:else if f.severity === 'warning'}
								<span class="severity-badge severity-warning">!</span>
							{/if}
						</div>
						<p>{@html renderLinkedMarkdown(f.description)}</p>
						{#if f.examples && f.examples.length > 0}
							<ul class="friction-examples">
								{#each f.examples as ex}
									<li>{@html renderLinkedMarkdown(ex)}</li>
								{/each}
							</ul>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- CLAUDE.md Suggestions -->
	{#if claudeMd && claudeMd.length > 0}
		<div class="section">
			<h2>Suggested CLAUDE.md Additions</h2>
			<p class="section-intro">Copy these into Claude Code to add them to your CLAUDE.md.</p>
			<div class="claude-md-list">
				{#each claudeMd as suggestion, i}
					<div class="claude-md-item">
						<pre class="claude-md-rule">{suggestion.rule}</pre>
						<div class="claude-md-actions">
							<button class="copy-btn" onclick={(e) => copyText(suggestion.rule, e.currentTarget as HTMLButtonElement)}>Copy</button>
						</div>
						<div class="claude-md-why">{@html renderLinkedMarkdown(suggestion.why)}</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Feature Recommendations -->
	{#if features && features.length > 0}
		<div class="section">
			<h2>CC Features to Try</h2>
			<div class="cards-list">
				{#each features as feat}
					<div class="card card-blue">
						<div class="feature-name">{feat.feature}</div>
						<h3>{feat.title}</h3>
						<p><strong>Why for you:</strong> {@html renderLinkedMarkdown(feat.why_for_you)}</p>
						{#if feat.setup_code}
							<div class="code-block-wrap">
								<pre class="code-block">{feat.setup_code}</pre>
								<button class="copy-btn" onclick={(e) => copyText(feat.setup_code ?? '', e.currentTarget as HTMLButtonElement)}>Copy</button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Workflow Patterns -->
	{#if patterns && patterns.length > 0}
		<div class="section">
			<h2>New Ways to Use Claude Code</h2>
			<div class="cards-list">
				{#each patterns as p}
					<div class="card card-cyan">
						<h3>{p.name}</h3>
						<p>{@html renderLinkedMarkdown(p.description)}</p>
						<p class="card-rationale">{@html renderLinkedMarkdown(p.rationale)}</p>
						<div class="code-block-wrap">
							<div class="prompt-label">Paste into Claude Code:</div>
							<pre class="code-block">{p.starter_prompt}</pre>
							<button class="copy-btn" onclick={(e) => copyText(p.starter_prompt, e.currentTarget as HTMLButtonElement)}>Copy</button>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Ambitious Workflows -->
	{#if ambitious && ambitious.length > 0}
		<div class="section">
			<h2>On the Horizon</h2>
			<div class="cards-list">
				{#each ambitious as a}
					<div class="card card-purple">
						<h3>{a.name}</h3>
						<p>{@html renderLinkedMarkdown(a.description)}</p>
						<p class="card-rationale">{@html renderLinkedMarkdown(a.rationale)}</p>
						<div class="code-block-wrap">
							<div class="prompt-label">Paste into Claude Code:</div>
							<pre class="code-block">{a.starter_prompt}</pre>
							<button class="copy-btn" onclick={(e) => copyText(a.starter_prompt, e.currentTarget as HTMLButtonElement)}>Copy</button>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Fun Ending -->

	<!-- Footer -->
	<div class="report-footer">
		<p>
			Generated {new Date(digest.created_at).toLocaleString()}
			| LLM: {(digest.analysis_prompt_tokens + digest.analysis_completion_tokens).toLocaleString()} tokens
		</p>
	</div>
{/if}

<style>
	.loading, .error { text-align: center; padding: 48px; color: #64748b; }
	.error { color: #dc2626; }
	.empty-state { text-align: center; padding: 64px; color: #64748b; }
	.empty-state h2 { color: #0f172a; margin-bottom: 12px; }
	.empty-state code { background: #f1f5f9; padding: 2px 6px; border-radius: 3px; }

	.report-header { margin-bottom: 24px; }
	.report-header h1 { font-size: 28px; font-weight: 700; color: #0f172a; }
	.project-label { font-family: monospace; color: #2563eb; margin-right: 8px; }
	.subtitle { color: #64748b; font-size: 14px; }
	.back-link { color: #64748b; text-decoration: none; font-size: 13px; display: inline-block; margin-bottom: 8px; }
	.back-link:hover { color: #2563eb; }

	/* At a Glance */
	.glance-banner { background: linear-gradient(135deg, #fef3c7, #fde68a); border: 1px solid #f59e0b; border-radius: 12px; padding: 24px; margin-bottom: 24px; }
	.glance-title { font-size: 18px; font-weight: 700; color: #92400e; margin-bottom: 16px; }
	.glance-grid { display: flex; flex-direction: column; gap: 12px; }
	.glance-item { font-size: 14px; color: #78350f; line-height: 1.6; }
	.glance-item strong { color: #92400e; }

	/* Stats Pills */
	.stats-pills { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
	.pill { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; text-align: center; flex: 1; min-width: 100px; }
	.pill-value { display: block; font-size: 24px; font-weight: 700; color: #0f172a; }
	.pill-label { font-size: 11px; color: #64748b; text-transform: uppercase; }

	/* Charts */
	.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
	.chart-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
	.chart-title { font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 12px; }
	.bar-row { display: flex; align-items: center; margin-bottom: 5px; }
	.bar-label { width: 90px; font-size: 11px; color: #475569; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.bar-track { flex: 1; height: 6px; background: #f1f5f9; border-radius: 3px; margin: 0 8px; }
	.bar-fill { height: 100%; border-radius: 3px; }
	.bar-blue { background: #2563eb; }
	.bar-green { background: #10b981; }
	.bar-purple { background: #8b5cf6; }
	.bar-red { background: #dc2626; }
	.bar-value { width: 32px; font-size: 11px; font-weight: 500; color: #64748b; text-align: right; }
	.bar-empty { font-size: 12px; color: #94a3b8; }

	/* Health Grid */
	.health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
	.health-card { background: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; text-decoration: none; color: inherit; }
	.health-card:hover { background: #f8fafc; }
	.health-top { display: flex; justify-content: space-between; align-items: center; }
	.health-grade { font-size: 18px; font-weight: 700; }
	.health-session-num { font-size: 11px; font-weight: 600; color: #2563eb; }
	.health-date { font-size: 12px; color: #64748b; }
	.health-meta { font-size: 11px; color: #94a3b8; }
	.show-more-btn { display: block; margin: 12px auto 0; background: none; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 16px; font-size: 13px; color: #64748b; cursor: pointer; }
	.show-more-btn:hover { background: #f8fafc; color: #334155; }

	/* Sections */
	.section { margin-bottom: 32px; }
	.section h2 { font-size: 20px; font-weight: 600; color: #0f172a; margin-bottom: 16px; }
	.section-intro { font-size: 13px; color: #64748b; margin-bottom: 12px; }

	/* Work Areas */
	.work-areas { display: flex; flex-direction: column; gap: 10px; }
	.work-area-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
	.work-area-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
	.work-area-name { font-weight: 600; font-size: 15px; color: #0f172a; }
	.work-area-count { font-size: 12px; color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 4px; }
	.work-area-desc { font-size: 14px; color: #475569; line-height: 1.5; }

	/* Persona */
	.persona-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; font-size: 14px; color: #475569; line-height: 1.7; }
	.persona-card :global(p) { margin-bottom: 12px; }
	.persona-card :global(strong) { color: #0f172a; }

	/* Cards */
	.cards-list { display: flex; flex-direction: column; gap: 12px; }
	.card { border: 1px solid; border-radius: 8px; padding: 16px; }
	.card h3 { font-size: 15px; font-weight: 600; color: #0f172a; margin-bottom: 6px; }
	.card p { font-size: 14px; color: #475569; line-height: 1.5; margin-bottom: 8px; }
	.card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
	.card-evidence { font-size: 12px; color: #64748b; }
	.card-rationale { font-size: 13px; color: #64748b; }
	.card-green { background: #f0fdf4; border-color: #86efac; }
	.card-red { background: #fef2f2; border-color: #fca5a5; }
	.card-blue { background: #eff6ff; border-color: #93c5fd; }
	.card-cyan { background: #ecfeff; border-color: #67e8f9; }
	.card-purple { background: linear-gradient(135deg, #faf5ff, #f5f3ff); border-color: #c4b5fd; }

	.feature-name { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #2563eb; margin-bottom: 4px; }
	.friction-examples { margin: 8px 0 0 20px; font-size: 13px; color: #334155; }
	.friction-examples li { margin-bottom: 4px; }

	.severity-badge { font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
	.severity-critical { background: #fef2f2; color: #dc2626; }
	.severity-warning { background: #fefce8; color: #ca8a04; }

	/* CLAUDE.md */
	.claude-md-list { display: flex; flex-direction: column; gap: 12px; }
	.claude-md-item { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; }
	.claude-md-rule { background: white; padding: 10px 14px; border-radius: 4px; font-size: 12px; color: #1e40af; border: 1px solid #bfdbfe; font-family: monospace; white-space: pre-wrap; word-break: break-word; margin: 0 0 8px 0; }
	.claude-md-actions { margin-bottom: 8px; }
	.claude-md-why { font-size: 12px; color: #64748b; line-height: 1.5; }

	/* Code blocks + copy */
	.code-block-wrap { position: relative; margin-top: 8px; }
	.code-block { background: #f8fafc; padding: 12px; border-radius: 6px; border: 1px solid #e2e8f0; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; margin: 0; }
	.prompt-label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: #64748b; margin-bottom: 6px; }
	.copy-btn { background: #e2e8f0; border: none; border-radius: 4px; padding: 4px 10px; font-size: 11px; cursor: pointer; color: #475569; }
	.copy-btn:hover { background: #cbd5e1; }

	/* Fun Ending */
	.callout { border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 14px; line-height: 1.5; }
	.callout-warn { background: #fefce8; border: 1px solid #fde68a; color: #854d0e; }
	.pill-warn { border-color: #fde68a; }
	.pill-warn .pill-value { color: #ca8a04; }
	.pill-alert { border-color: #fca5a5; }
	.pill-alert .pill-value { color: #dc2626; font-size: 14px; }

	/* Footer */
	.report-footer { text-align: center; padding: 24px; color: #94a3b8; font-size: 12px; }

	@media (max-width: 768px) {
		.charts-row { grid-template-columns: 1fr; }
		.stats-pills { flex-direction: column; }
	}
</style>
