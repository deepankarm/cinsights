<script lang="ts">
	import { onMount } from 'svelte';
	import { getProjects, type ProjectRead } from '$lib/api';

	let projects: ProjectRead[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);

	onMount(async () => {
		try {
			projects = await getProjects();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load projects';
		} finally {
			loading = false;
		}
	});

	function formatTokens(n: number): string {
		if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
		if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
		return n.toString();
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString();
	}
</script>

<svelte:head>
	<title>Projects - cinsights</title>
</svelte:head>

<h1>Projects</h1>
<p class="subtitle">Per-project analysis of your Claude Code usage</p>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="error">{error}</div>
{:else if projects.length === 0}
	<div class="empty">
		<p>No projects detected yet.</p>
		<p>Run <code>cinsights analyze</code> to detect projects from file paths in your sessions.</p>
	</div>
{:else}
	<div class="project-grid">
		{#each projects as project}
			<div class="project-card">
				<div class="project-header">
					<h2 class="project-name">{project.name}</h2>
					{#if project.has_digest}
						<span class="digest-badge">Report ready</span>
					{/if}
				</div>

				<div class="project-stats">
					<div class="stat">
						<span class="stat-value">{project.session_count}</span>
						<span class="stat-label">sessions</span>
					</div>
					<div class="stat">
						<span class="stat-value">{formatTokens(project.total_tokens)}</span>
						<span class="stat-label">tokens</span>
					</div>
					<div class="stat">
						<span class="stat-value">{project.total_tool_calls}</span>
						<span class="stat-label">tool calls</span>
					</div>
				</div>

				{#if project.top_tools.length > 0}
					<div class="project-tools">
						{#each project.top_tools as tool}
							<span class="tool-chip">{tool}</span>
						{/each}
					</div>
				{/if}

				<div class="project-footer">
					<span class="last-active">Last active: {formatDate(project.latest_session)}</span>
					<div class="project-actions">
						<a href="/projects/{encodeURIComponent(project.name)}" class="action-btn">
							Dashboard
						</a>
						{#if project.has_digest}
							<a href="/report?project={encodeURIComponent(project.name)}" class="action-link">
								Report
							</a>
						{/if}
					</div>
				</div>
			</div>
		{/each}
	</div>
{/if}

<style>
	h1 { font-size: 28px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
	.subtitle { color: #64748b; font-size: 14px; margin-bottom: 24px; }
	.loading, .error { text-align: center; padding: 48px; color: #64748b; }
	.error { color: #dc2626; }
	.empty { text-align: center; padding: 64px; color: #64748b; }
	.empty code { background: #f1f5f9; padding: 2px 6px; border-radius: 3px; }

	.project-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 16px;
	}

	.project-card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 10px;
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.project-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.project-name {
		font-size: 18px;
		font-weight: 700;
		color: #0f172a;
		font-family: monospace;
	}

	.digest-badge {
		font-size: 11px;
		font-weight: 600;
		color: #16a34a;
		background: #f0fdf4;
		border: 1px solid #bbf7d0;
		padding: 2px 8px;
		border-radius: 4px;
	}

	.project-stats {
		display: flex;
		gap: 20px;
	}

	.stat {
		display: flex;
		flex-direction: column;
	}

	.stat-value {
		font-size: 20px;
		font-weight: 700;
		color: #0f172a;
	}

	.stat-label {
		font-size: 11px;
		color: #64748b;
		text-transform: uppercase;
	}

	.project-tools {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	.tool-chip {
		font-size: 11px;
		font-family: monospace;
		background: #f1f5f9;
		color: #475569;
		padding: 2px 8px;
		border-radius: 4px;
	}

	.project-footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-top: auto;
		padding-top: 10px;
		border-top: 1px solid #f1f5f9;
	}

	.last-active {
		font-size: 12px;
		color: #94a3b8;
	}

	.project-actions {
		display: flex;
		gap: 12px;
		align-items: center;
	}

	.action-btn {
		background: #2563eb;
		color: white;
		border: none;
		border-radius: 6px;
		padding: 6px 14px;
		font-size: 12px;
		font-weight: 500;
		text-decoration: none;
	}

	.action-btn:hover {
		background: #1d4ed8;
	}

	.action-link {
		font-size: 12px;
		color: #64748b;
		text-decoration: none;
	}

	.action-link:hover {
		color: #2563eb;
	}
</style>
