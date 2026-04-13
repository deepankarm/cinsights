<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getTrends, getUsers, getSessions, getTokenDistribution, type TrendPoint, type UserSummary, type TokenDistribution } from '$lib/api';
	import type { SessionRead } from '$lib/types';
	import { fmtTokens, fmtDur, fmtNum, fmtDate, fmtDuration, avatarColor } from '$lib/format';
	import HeroMetrics from '$lib/components/HeroMetrics.svelte';
	import TrendCharts from '$lib/components/TrendCharts.svelte';

	const userId = $derived(decodeURIComponent(page.params.id));

	let user: UserSummary | null = $state(null);
	let trends: TrendPoint[] = $state([]);
	let sessions: SessionRead[] = $state([]);
	let tokenDist: TokenDistribution | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let hoveredMetric: string | null = $state(null);
	let expandedProjects: Set<string> = $state(new Set());

	onMount(async () => {
		try {
			const [users, trendData, sessionData, td] = await Promise.all([
				getUsers(), getTrends(undefined, userId), getSessions(0, 500, undefined, userId), getTokenDistribution(undefined, userId),
			]);
			user = users.find(u => u.user_id === userId) ?? null;
			trends = trendData;
			sessions = sessionData;
			tokenDist = td;
			if (!user) error = `User not found: ${userId}`;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load user';
		} finally {
			loading = false;
		}
	});

	const daysTracked = $derived(new Set(trends.map(t => t.date)).size);
	const totalTokens = $derived(trends.reduce((s, t) => s + t.total_tokens, 0));

	const heroMetrics = $derived(user ? [
		{ value: String(user.session_count), label: 'Sessions', sub: `${user.analyzed_count} analyzed · ${user.indexed_count} indexed` },
		{ value: fmtTokens(totalTokens), label: 'Total Tokens', sub: 'across all sessions' },
		{ value: String(user.projects.length), label: 'Projects', sub: user.projects.slice(0, 3).join(', ') || 'none' },
		{ value: String(daysTracked), label: 'Days Active', sub: user.agents.join(', ') },
	] : []);

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

	type QM = { label: string; value: string };
	const qualityMetrics = $derived<QM[]>(user ? [
		{ label: 'Read:Edit', value: fmtNum(user.avg_read_edit_ratio) },
		{ label: 'Blind edits', value: fmtNum(user.avg_edits_without_read_pct, '%') },
		{ label: 'Research:Mut', value: fmtNum(user.avg_research_mutation_ratio) },
		{ label: 'Error rate', value: fmtNum(user.avg_error_rate, '%') },
		{ label: 'Write vs Edit', value: fmtNum(user.avg_write_vs_edit_pct, '%') },
		{ label: 'Thrashing', value: fmtNum(user.avg_repeated_edits) },
		{ label: 'Subagents', value: fmtNum(user.avg_subagent_spawn_rate, '%') },
		{ label: 'Ctx pressure', value: fmtNum(user.avg_context_pressure) },
		{ label: 'Tools/turn', value: fmtNum(user.avg_tool_calls_per_turn) },
		{ label: 'Avg duration', value: fmtDur(user.avg_duration_ms) },
	] : []);

	const sessionsByProject = $derived.by(() => {
		const groups: Record<string, SessionRead[]> = {};
		for (const s of sessions) {
			(groups[s.project_name ?? 'Unknown'] ??= []).push(s);
		}
		return Object.entries(groups).sort(([, a], [, b]) => b.length - a.length);
	});

	function toggleProject(name: string) {
		const next = new Set(expandedProjects);
		if (next.has(name)) next.delete(name); else next.add(name);
		expandedProjects = next;
	}

	function displayId(id: string): string {
		if (id.startsWith('local:')) return id.split(':').slice(2).join(':').slice(0, 16);
		if (id.startsWith('entireio:')) return id.split(':')[1].slice(0, 8);
		return id.slice(0, 8);
	}
	function srcColor(s: string): string {
		return s === 'local' ? '#7c3aed' : s === 'entireio' ? '#0891b2' : s === 'phoenix' ? '#ea580c' : '#64748b';
	}
	function statColor(s: string): string {
		return s === 'analyzed' ? '#16a34a' : s === 'indexed' ? '#8b5cf6' : '#64748b';
	}
	function statIcon(s: string): string {
		return s === 'analyzed' ? '●' : s === 'indexed' ? '○' : s === 'failed' ? '✗' : '·';
	}
</script>

<svelte:head><title>{user?.display_name ?? 'User'} — cinsights</title></svelte:head>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="loading" style="color: #dc2626">{error}</div>
{:else if user}
	<div class="user-banner">
		<span class="avatar-lg" style="background: {avatarColor(user.display_name)}">{user.display_name[0].toUpperCase()}</span>
		<div class="banner-info">
			<h1>{user.display_name}</h1>
			<p class="user-email">{user.user_id}</p>
			<div class="banner-tags">
				{#each user.agents as a}<span class="tag agent">{a}</span>{/each}
				{#each user.sources as s}<span class="tag source">{s}</span>{/each}
			</div>
		</div>
	</div>

	<!-- Quality metrics with hover descriptions -->
	<div class="quality-bar">
		{#each qualityMetrics as m}
			<div class="qb-item"
				onmouseenter={() => hoveredMetric = m.label}
				onmouseleave={() => hoveredMetric = null}>
				<span class="qb-val">{m.value}</span>
				<span class="qb-label">{m.label}</span>
			</div>
		{/each}
	</div>
	{#if hoveredMetric && metricDescs[hoveredMetric]}
		<div class="metric-tooltip">
			<strong>{hoveredMetric}</strong>: {metricDescs[hoveredMetric]}
		</div>
	{/if}

	<HeroMetrics metrics={heroMetrics} />

	<TrendCharts {trends} {tokenDist} />

	<!-- Sessions as expandable project cards -->
	{#if sessionsByProject.length > 0}
		<div class="section">
			<h2>Sessions <span class="dim">({sessions.length} total)</span></h2>
			<div class="project-list">
				{#each sessionsByProject as [project, projectSessions]}
					{@const isOpen = expandedProjects.has(project)}
					{@const preview = projectSessions.slice(0, 5)}
					{@const analyzed = projectSessions.filter(s => s.status === 'analyzed').length}
					<div class="project-group">
						<button class="project-header" onclick={() => toggleProject(project)}>
							<span class="ph-arrow">{isOpen ? '▾' : '▸'}</span>
							<span class="ph-name">{project}</span>
							<span class="ph-count">{projectSessions.length} sessions</span>
							{#if analyzed > 0}
								<span class="ph-analyzed">{analyzed} analyzed</span>
							{/if}
							<span class="ph-tokens">{fmtTokens(projectSessions.reduce((s, x) => s + x.total_tokens, 0))}</span>
						</button>
						{#if isOpen}
							<div class="project-sessions">
								{#each projectSessions as s}
									<a href="/sessions/{s.id}" class="session-row">
										<span class="sr-id">{displayId(s.id)}</span>
										<span class="sr-source" style="color: {srcColor(s.source ?? 'phoenix')}">{s.source ?? 'phoenix'}</span>
										<span class="sr-time">{fmtDate(s.start_time)}</span>
										<span class="sr-dur">{fmtDuration(s.start_time, s.end_time)}</span>
										<span class="sr-tools">{s.tool_call_count || '-'} tools</span>
										<span class="sr-tokens">{fmtTokens(s.total_tokens)}</span>
										<span class="sr-status" style="color: {statColor(s.status)}">{statIcon(s.status)} {s.status}</span>
									</a>
								{/each}
							</div>
						{:else}
							<div class="project-preview">
								{#each preview as s}
									<a href="/sessions/{s.id}" class="preview-chip">
										<span class="pc-id">{displayId(s.id)}</span>
										<span class="pc-dur">{fmtDuration(s.start_time, s.end_time)}</span>
										<span class="pc-status" style="color: {statColor(s.status)}">{statIcon(s.status)}</span>
									</a>
								{/each}
								{#if projectSessions.length > 5}
									<button class="preview-more" onclick={() => toggleProject(project)}>+{projectSessions.length - 5} more</button>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}
{/if}

<style>
	.loading { text-align: center; padding: 80px; color: #94a3b8; }

	.user-banner { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
	.banner-info { flex: 1; }
	.avatar-lg { width: 52px; height: 52px; border-radius: 14px; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 24px; flex-shrink: 0; }
	h1 { font-size: 24px; font-weight: 800; color: #232326; line-height: 1.2; }
	.user-email { font-size: 13px; color: #94a3b8; margin-bottom: 8px; }
	.banner-tags { display: flex; flex-wrap: wrap; gap: 4px; }
	.tag { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 5px; border: 1px solid; }
	.tag.agent { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
	.tag.source { background: #f0fdf4; color: #166534; border-color: #bbf7d0; }

	.quality-bar {
		display: flex; flex-wrap: wrap; gap: 0; margin-bottom: 4px;
		background: white; border: 1px solid #e8e5e0; border-radius: 10px; overflow: hidden;
	}
	.qb-item { text-align: center; flex: 1; min-width: 80px; padding: 12px 8px; border-right: 1px solid #f1f5f9; cursor: help; transition: background 0.1s; }
	.qb-item:last-child { border-right: none; }
	.qb-item:hover { background: #f0f4ff; }
	.qb-val { display: block; font-size: 16px; font-weight: 700; color: #232326; }
	.qb-label { display: block; font-size: 9px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }

	.metric-tooltip {
		background: #1e293b; color: #e2e8f0; font-size: 12px; padding: 8px 12px; border-radius: 6px;
		margin-bottom: 16px; line-height: 1.5;
	}
	.metric-tooltip strong { color: white; }

	.section { margin-bottom: 28px; }
	h2 { font-size: 17px; font-weight: 700; color: #232326; margin-bottom: 12px; }
	.dim { font-size: 13px; font-weight: 400; color: #94a3b8; }

	/* Project-based sessions */
	.project-list { display: flex; flex-direction: column; gap: 8px; }
	.project-group { background: white; border: 1px solid #e8e5e0; border-radius: 10px; overflow: hidden; }
	.project-header {
		display: flex; align-items: center; gap: 10px; width: 100%; padding: 12px 16px;
		background: none; border: none; cursor: pointer; text-align: left;
		font-size: 14px; transition: background 0.1s;
	}
	.project-header:hover { background: #f8fafc; }
	.ph-arrow { font-size: 12px; color: #94a3b8; width: 16px; }
	.ph-name { font-weight: 700; color: #232326; font-family: monospace; }
	.ph-count { font-size: 12px; color: #64748b; }
	.ph-analyzed { font-size: 11px; color: #16a34a; background: #f0fdf4; padding: 1px 6px; border-radius: 3px; }
	.ph-tokens { font-size: 12px; color: #94a3b8; margin-left: auto; font-family: monospace; }

	.project-preview { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 16px 12px; }
	.preview-chip {
		display: flex; align-items: center; gap: 6px; padding: 3px 10px;
		background: #f8fafc; border-radius: 5px; font-size: 11px; text-decoration: none; color: #475569;
		transition: background 0.1s;
	}
	.preview-chip:hover { background: #eff6ff; }
	.pc-id { font-family: monospace; color: #2563eb; font-weight: 500; }
	.pc-dur { color: #94a3b8; }
	.preview-more { background: none; border: 1px dashed #d4d4d8; border-radius: 5px; padding: 3px 10px; font-size: 11px; color: #3b82f6; cursor: pointer; }

	.project-sessions { border-top: 1px solid #f1f5f9; }
	.session-row {
		display: grid; grid-template-columns: 140px 70px 100px 70px 70px 70px 90px;
		gap: 8px; padding: 8px 16px; text-decoration: none; font-size: 12px; color: #334155;
		border-bottom: 1px solid #f8fafc; align-items: center; transition: background 0.1s;
	}
	.session-row:last-child { border-bottom: none; }
	.session-row:hover { background: #f8fafc; }
	.sr-id { font-family: monospace; color: #2563eb; font-weight: 500; }
	.sr-source { font-weight: 600; font-size: 11px; }
	.sr-time { color: #64748b; }
	.sr-dur { font-family: monospace; color: #475569; }
	.sr-tools { color: #64748b; }
	.sr-tokens { font-family: monospace; color: #475569; text-align: right; }
	.sr-status { font-size: 11px; text-align: right; }
</style>
