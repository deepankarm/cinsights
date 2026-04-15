<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getSessions, getStats } from '$lib/api';
	import type { SessionRead, StatsResponse } from '$lib/types';
	import { fmtTokens } from '$lib/format';
	import SessionTable from '$lib/components/SessionTable.svelte';

	let sessions: SessionRead[] = $state([]);
	let stats: StatsResponse | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);

	const filterUser = $derived(page.url.searchParams.get('user'));
	const filterProject = $derived(page.url.searchParams.get('project'));
	const filterLabel = $derived(
		filterUser ? `User: ${filterUser.split('@')[0]}` :
		filterProject ? `Project: ${filterProject}` : null
	);

	onMount(async () => {
		try {
			[sessions, stats] = await Promise.all([
				getSessions(0, 500, undefined, filterUser ?? undefined, filterProject ?? undefined),
				getStats(),
			]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load data';
		} finally {
			loading = false;
		}
	});

	const sessionsByProject = $derived.by(() => {
		const groups: Record<string, SessionRead[]> = {};
		for (const s of sessions) {
			const key = s.project_name ?? 'Unknown';
			(groups[key] ??= []).push(s);
		}
		return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
	});
</script>

<svelte:head>
	<title>cinsights - Sessions</title>
</svelte:head>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="error">{error}</div>
{:else}
	{#if filterLabel}
		<div class="filter-bar">
			<span class="filter-label">{filterLabel}</span>
			<span class="filter-count">{sessions.length} sessions</span>
			<a href="/sessions" class="filter-clear">Clear filter</a>
		</div>
	{/if}
	{#if stats}
		<div class="stats-row">
			<div class="stat-card">
				<div class="stat-value">{stats.total_sessions}</div>
				<div class="stat-label">Sessions</div>
			</div>
			<div class="stat-card">
				<div class="stat-value">{stats.analyzed_sessions}</div>
				<div class="stat-label">Analyzed</div>
			</div>
			<div class="stat-card">
				<div class="stat-value">{stats.total_insights}</div>
				<div class="stat-label">Insights</div>
			</div>
			<div class="stat-card">
				<div class="stat-value">{fmtTokens(stats.total_tool_calls)}</div>
				<div class="stat-label">Tool Calls</div>
			</div>
		</div>

		{#if Object.keys(stats.top_tools).length > 0}
			<div class="section">
				<h2>Top Tools <span class="top-tools-hint">({stats.distinct_tool_count} distinct, top 10 shown)</span></h2>
				<div class="tools-grid">
					{#each Object.entries(stats.top_tools) as [name, count]}
						<div class="tool-chip">
							<span class="tool-name">{name}</span>
							<span class="tool-count">{count}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}

	<div class="section">
		<h2>Sessions</h2>
		{#if sessions.length === 0}
			<div class="empty">
				No sessions found. Run <code>cinsights analyze</code> to import sessions.
			</div>
		{:else}
			{#each sessionsByProject as [project, projectSessions]}
				<h3 class="project-heading">{project} <span class="project-count">({projectSessions.length})</span></h3>
				<SessionTable sessions={projectSessions} />
			{/each}
		{/if}
	</div>
{/if}

<style>
	.filter-bar {
		display: flex; align-items: center; gap: 12px;
		padding: 10px 16px; background: #eff6ff; border: 1px solid #bfdbfe;
		border-radius: 8px; margin-bottom: 16px;
	}
	.filter-label { font-size: 14px; font-weight: 600; color: #1e40af; }
	.filter-count { font-size: 12px; color: #3b82f6; }
	.filter-clear { font-size: 12px; color: #64748b; margin-left: auto; text-decoration: none; }
	.filter-clear:hover { color: #dc2626; }

	.loading, .error { text-align: center; padding: 48px; color: #64748b; }
	.error { color: #dc2626; }

	.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
	.stat-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; text-align: center; }
	.stat-value { font-size: 28px; font-weight: 700; color: #0f172a; }
	.stat-label { font-size: 12px; color: #64748b; text-transform: uppercase; margin-top: 4px; }

	.section { margin-bottom: 32px; }
	h2 { font-size: 18px; font-weight: 600; color: #0f172a; margin-bottom: 16px; }
	.top-tools-hint { font-size: 12px; font-weight: 400; color: #94a3b8; }

	.tools-grid { display: flex; flex-wrap: wrap; gap: 8px; }
	.tool-chip { background: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 12px; display: flex; gap: 8px; align-items: center; }
	.tool-name { font-size: 13px; font-weight: 500; }
	.tool-count { font-size: 12px; color: #64748b; background: #f1f5f9; padding: 1px 6px; border-radius: 4px; }

	.project-heading { font-size: 15px; font-weight: 600; color: #334155; margin-top: 24px; margin-bottom: 8px; }
	.project-heading:first-of-type { margin-top: 0; }
	.project-count { font-weight: 400; color: #94a3b8; font-size: 13px; }

	.empty { padding: 48px; text-align: center; color: #64748b; background: white; border: 1px solid #e2e8f0; border-radius: 8px; }
	.empty code { background: #f1f5f9; padding: 2px 6px; border-radius: 3px; font-size: 13px; }

	@media (max-width: 768px) { .stats-row { grid-template-columns: repeat(2, 1fr); } }
</style>
