<script lang="ts">
	import { onMount } from 'svelte';
	import { getSessions, getStats } from '$lib/api';
	import type { SessionRead, StatsResponse } from '$lib/types';

	let sessions: SessionRead[] = $state([]);
	let stats: StatsResponse | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);

	onMount(async () => {
		try {
			[sessions, stats] = await Promise.all([getSessions(), getStats()]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load data';
		} finally {
			loading = false;
		}
	});

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

	function statusColor(status: string): string {
		switch (status) {
			case 'analyzed':
				return '#16a34a';
			case 'pending':
				return '#eab308';
			case 'failed':
				return '#dc2626';
			default:
				return '#64748b';
		}
	}
</script>

<svelte:head>
	<title>cinsights - Dashboard</title>
</svelte:head>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="error">{error}</div>
{:else}
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
				<div class="stat-value">{Object.keys(stats.top_tools).length}</div>
				<div class="stat-label">Tools Used</div>
			</div>
		</div>

		{#if Object.keys(stats.top_tools).length > 0}
			<div class="section">
				<h2>Top Tools</h2>
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
				No sessions found. Run <code>cinsights analyze</code> to import sessions from Phoenix.
			</div>
		{:else}
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th>Time</th>
							<th>Model</th>
							<th>Duration</th>
							<th>Tools</th>
							<th>Tokens</th>
							<th>Insights</th>
							<th>Status</th>
						</tr>
					</thead>
					<tbody>
						{#each sessions as session}
							<tr>
								<td>
									<a href="/sessions/{session.id}" class="session-link">
										{formatDate(session.start_time)}
									</a>
								</td>
								<td class="mono">{session.model ?? '-'}</td>
								<td>{formatDuration(session.start_time, session.end_time)}</td>
								<td>{session.tool_call_count}</td>
								<td>{session.total_tokens.toLocaleString()}</td>
								<td>{session.insight_count}</td>
								<td>
									<span class="status-badge" style="color: {statusColor(session.status)}">
										{session.status}
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>
{/if}

<style>
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
		overflow: hidden;
	}
	table {
		width: 100%;
		border-collapse: collapse;
	}
	th {
		text-align: left;
		padding: 12px 16px;
		font-size: 12px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		border-bottom: 1px solid #e2e8f0;
		background: #f8fafc;
	}
	td {
		padding: 12px 16px;
		font-size: 14px;
		border-bottom: 1px solid #f1f5f9;
	}
	tr:last-child td {
		border-bottom: none;
	}
	tr:hover {
		background: #f8fafc;
	}
	.session-link {
		color: #2563eb;
		text-decoration: none;
		font-weight: 500;
	}
	.session-link:hover {
		text-decoration: underline;
	}
	.mono {
		font-family: monospace;
		font-size: 12px;
	}
	.status-badge {
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
	}
	.empty {
		padding: 48px;
		text-align: center;
		color: #64748b;
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
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
