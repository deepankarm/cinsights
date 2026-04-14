<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getSessions, getStats } from '$lib/api';
	import type { SessionRead, StatsResponse } from '$lib/types';

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

	function formatDate(iso: string): string {
		const d = new Date(iso);
		const day = d.getDate().toString().padStart(2, '0');
		const mon = d.toLocaleString('en', { month: 'short' });
		const h = d.getHours().toString().padStart(2, '0');
		const m = d.getMinutes().toString().padStart(2, '0');
		return `${day} ${mon} ${h}:${m}`;
	}

	function formatDurationMs(ms: number): string {
		if (ms < 1000) return '<1s';
		const mins = Math.floor(ms / 60000);
		const secs = Math.floor((ms % 60000) / 1000);
		if (mins >= 60) return `${Math.floor(mins / 60)}h ${mins % 60}m`;
		if (mins > 0) return `${mins}m ${secs}s`;
		return `${secs}s`;
	}

	function formatActiveDuration(session: SessionRead): string {
		if (session.active_duration_ms) return formatDurationMs(session.active_duration_ms);
		if (!session.end_time) return '-';
		const ms = new Date(session.end_time).getTime() - new Date(session.start_time).getTime();
		return formatDurationMs(ms);
	}

	function formatTokens(n: number): string {
		if (n === 0) return '-';
		if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
		if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
		return n.toString();
	}

	function displaySessionId(id: string): string {
		if (id.startsWith('local:')) {
			// local:claude-code:uuid or local:codex:rollout-...
			return id.split(':').slice(2).join(':').slice(0, 18);
		}
		if (id.startsWith('entireio:')) {
			return id.split(':')[1].slice(0, 8);
		}
		return id.slice(0, 8);
	}

	function sourceLabel(session: SessionRead): string {
		return session.source ?? 'phoenix';
	}

	function sourceColor(source: string): string {
		switch (source) {
			case 'local': return '#7c3aed';
			case 'entireio': return '#0891b2';
			case 'phoenix': return '#ea580c';
			default: return '#64748b';
		}
	}

	function agentColor(agent: string | null): string {
		switch (agent) {
			case 'claude-code': return '#c2410c';
			case 'codex': return '#15803d';
			case 'copilot': return '#1d4ed8';
			default: return '#64748b';
		}
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'analyzed': return '#16a34a';
			case 'indexed': return '#8b5cf6';
			case 'pending': return '#ca8a04';
			case 'failed': return '#dc2626';
			default: return '#64748b';
		}
	}

	function statusIcon(status: string): string {
		switch (status) {
			case 'analyzed': return '●';
			case 'indexed': return '○';
			case 'pending': return '◌';
			case 'failed': return '✗';
			default: return '·';
		}
	}

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
	<title>cinsights - Dashboard</title>
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
				<div class="stat-value">{formatTokens(stats.total_tool_calls)}</div>
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
				<div class="table-wrap">
					<table>
						<thead>
							<tr>
								<th class="col-session">Session</th>
								<th class="col-source">Source</th>
								<th class="col-agent">Agent</th>
								<th class="col-time">Time</th>
								<th class="col-model">Model</th>
								<th class="col-duration">Active</th>
								<th class="col-num">Tools</th>
								<th class="col-num">Tokens</th>
								<th class="col-num">Insights</th>
								<th class="col-status">Status</th>
							</tr>
						</thead>
						<tbody>
							{#each projectSessions as session}
								<tr>
									<td class="cell-session">
										<a href="/sessions/{session.id}" class="session-link" title={session.id}>
											{displaySessionId(session.id)}
										</a>
									</td>
									<td>
										<span class="badge" style="background: {sourceColor(sourceLabel(session))}15; color: {sourceColor(sourceLabel(session))}; border-color: {sourceColor(sourceLabel(session))}30">
											{sourceLabel(session)}
										</span>
									</td>
									<td>
										<span class="badge" style="background: {agentColor(session.agent_type)}10; color: {agentColor(session.agent_type)}; border-color: {agentColor(session.agent_type)}25">
											{session.agent_type ?? '-'}
										</span>
									</td>
									<td class="cell-dim">{formatDate(session.start_time)}</td>
									<td class="cell-mono">{session.model ?? '-'}</td>
									<td class="cell-mono">{formatActiveDuration(session)}</td>
									<td class="cell-num">{session.tool_call_count || '-'}</td>
									<td class="cell-num">{formatTokens(session.total_tokens)}</td>
									<td class="cell-num">{session.insight_count || '-'}</td>
									<td>
										<span class="status" style="color: {statusColor(session.status)}">
											{statusIcon(session.status)} {session.status}
										</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/each}
		{/if}
	</div>
{/if}

<style>
	.filter-bar {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 16px;
		background: #eff6ff;
		border: 1px solid #bfdbfe;
		border-radius: 8px;
		margin-bottom: 16px;
	}
	.filter-label { font-size: 14px; font-weight: 600; color: #1e40af; }
	.filter-count { font-size: 12px; color: #3b82f6; }
	.filter-clear { font-size: 12px; color: #64748b; margin-left: auto; text-decoration: none; }
	.filter-clear:hover { color: #dc2626; }

	.loading,
	.error {
		text-align: center;
		padding: 48px;
		color: #64748b;
	}
	.error {
		color: #dc2626;
	}
	.stats-row {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
		margin-bottom: 32px;
	}
	.stat-card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 20px;
		text-align: center;
	}
	.stat-value {
		font-size: 28px;
		font-weight: 700;
		color: #0f172a;
	}
	.stat-label {
		font-size: 12px;
		color: #64748b;
		text-transform: uppercase;
		margin-top: 4px;
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
	.top-tools-hint {
		font-size: 12px;
		font-weight: 400;
		color: #94a3b8;
	}
	.tools-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.tool-chip {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 6px;
		padding: 6px 12px;
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.tool-name {
		font-size: 13px;
		font-weight: 500;
	}
	.tool-count {
		font-size: 12px;
		color: #64748b;
		background: #f1f5f9;
		padding: 1px 6px;
		border-radius: 4px;
	}
	.table-wrap {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		overflow-x: auto;
		margin-bottom: 8px;
	}
	table {
		width: 100%;
		min-width: 900px;
		border-collapse: collapse;
	}
	th {
		text-align: left;
		padding: 10px 14px;
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		border-bottom: 2px solid #e2e8f0;
		background: #f8fafc;
		white-space: nowrap;
	}
	td {
		padding: 9px 14px;
		font-size: 13px;
		border-bottom: 1px solid #f1f5f9;
		color: #334155;
	}
	tr:last-child td {
		border-bottom: none;
	}
	tr:hover {
		background: #f8fafc;
	}

	/* Column widths */
	.col-session { min-width: 160px; }
	.col-source { min-width: 70px; }
	.col-agent { min-width: 100px; }
	.col-time { min-width: 110px; }
	.col-model { min-width: 120px; }
	.col-duration { min-width: 80px; }
	.col-num { min-width: 60px; text-align: right; }
	.col-status { min-width: 90px; }

	.cell-session {
		font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
		font-size: 12px;
	}
	.session-link {
		color: #2563eb;
		text-decoration: none;
		font-weight: 500;
		white-space: nowrap;
	}
	.session-link:hover {
		text-decoration: underline;
		color: #1d4ed8;
	}
	.cell-mono {
		font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
		font-size: 12px;
		color: #475569;
	}
	.cell-dim {
		font-size: 12px;
		color: #64748b;
		white-space: nowrap;
	}
	.cell-num {
		text-align: right;
		font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
		font-size: 12px;
		color: #475569;
	}

	.badge {
		display: inline-block;
		font-size: 11px;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 4px;
		border: 1px solid;
		white-space: nowrap;
	}
	.status {
		font-size: 12px;
		font-weight: 500;
		white-space: nowrap;
	}

	.empty {
		padding: 48px;
		text-align: center;
		color: #64748b;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
	}
	.project-heading {
		font-size: 15px;
		font-weight: 600;
		color: #334155;
		margin-top: 24px;
		margin-bottom: 8px;
	}
	.project-heading:first-of-type {
		margin-top: 0;
	}
	.project-count {
		font-weight: 400;
		color: #94a3b8;
		font-size: 13px;
	}
	.empty code {
		background: #f1f5f9;
		padding: 2px 6px;
		border-radius: 3px;
		font-size: 13px;
	}
	@media (max-width: 768px) {
		.stats-row {
			grid-template-columns: repeat(2, 1fr);
		}
	}
</style>
