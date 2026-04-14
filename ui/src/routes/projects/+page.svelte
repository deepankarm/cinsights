<script lang="ts">
	import { onMount } from 'svelte';
	import { getProjects, type ProjectRead } from '$lib/api';
	import { fmtTokens } from '$lib/format';

	let projects: ProjectRead[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);
	let hoveredProject: ProjectRead | null = $state(null);
	let hoverPos = $state({ x: 0, y: 0 });

	onMount(async () => {
		try {
			projects = await getProjects();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load projects';
		} finally {
			loading = false;
		}
	});

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
	}
</script>

<svelte:head>
	<title>Projects — cinsights</title>
</svelte:head>

<h1>Projects</h1>
<p class="subtitle">Per-project analysis of your coding agent usage</p>

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
			<a href="/projects/{encodeURIComponent(project.name)}" class="project-card"
				onmouseenter={(e) => { hoveredProject = project; hoverPos = { x: e.clientX, y: e.clientY }; }}
				onmousemove={(e) => { hoverPos = { x: e.clientX, y: e.clientY }; }}
				onmouseleave={() => { hoveredProject = null; }}>
				<div class="card-top">
					<span class="project-name">{project.name}</span>
					{#if project.has_digest}<span class="badge insights">Insights</span>{/if}
				</div>
				<div class="card-stats">
					<div class="stat">
						<span class="stat-val">{project.session_count}</span>
						<span class="stat-label">sessions</span>
					</div>
					<div class="stat">
						<span class="stat-val">{project.developer_count}</span>
						<span class="stat-label">{project.developer_count === 1 ? 'dev' : 'devs'}</span>
					</div>
					<div class="stat">
						<span class="stat-val">{fmtTokens(project.total_tokens)}</span>
						<span class="stat-label">tokens</span>
					</div>
				</div>
				{#if project.top_tools.length > 0}
					<div class="card-tools">
						{#each project.top_tools.slice(0, 4) as tool}
							<span class="tool-chip">{tool}</span>
						{/each}
					</div>
				{/if}
				<div class="card-footer">
					<span class="last-active">{formatDate(project.latest_session)}</span>
					{#if project.analyzed_count > 0}
						<span class="analyzed-badge">{project.analyzed_count} analyzed</span>
					{/if}
				</div>
			</a>
		{/each}
	</div>

	{#if hoveredProject}
		{@const p = hoveredProject}
		{@const panelW = 300}
		{@const panelH = 220}
		{@const px = Math.min(hoverPos.x + 16, (typeof window !== 'undefined' ? window.innerWidth : 1200) - panelW - 20)}
		{@const py = Math.min(hoverPos.y - panelH / 2, (typeof window !== 'undefined' ? window.innerHeight : 800) - panelH - 20)}
		<div class="hover-panel" style="left: {Math.max(8, px)}px; top: {Math.max(8, py)}px; width: {panelW}px">
			<div class="hp-name">{p.name}</div>
			<div class="hp-grid">
				<div class="hp-item"><span class="hp-val">{p.session_count}</span><span class="hp-label">Sessions</span></div>
				<div class="hp-item"><span class="hp-val">{p.analyzed_count}</span><span class="hp-label">Analyzed</span></div>
				<div class="hp-item"><span class="hp-val">{p.session_count - p.analyzed_count}</span><span class="hp-label">Indexed</span></div>
				<div class="hp-item"><span class="hp-val">{p.developer_count}</span><span class="hp-label">Developers</span></div>
				<div class="hp-item"><span class="hp-val">{p.active_days}</span><span class="hp-label">Active days</span></div>
				<div class="hp-item"><span class="hp-val">{fmtTokens(p.total_tokens)}</span><span class="hp-label">Tokens</span></div>
			</div>
			{#if p.top_tools.length > 0}
				<div class="hp-tools">
					{#each p.top_tools as t}<span class="hp-tool">{t}</span>{/each}
				</div>
			{/if}
			{#if p.languages.length > 0}
				<div class="hp-langs">
					{#each p.languages as l}<span class="hp-lang">{l}</span>{/each}
				</div>
			{/if}
			{#if p.has_digest}<div class="hp-digest">Insights available</div>{/if}
		</div>
	{/if}
{/if}

<style>
	h1 { font-size: 24px; font-weight: 800; color: #232326; margin-bottom: 4px; }
	.subtitle { color: #a1a1aa; font-size: 13px; margin-bottom: 24px; }
	.loading, .error { text-align: center; padding: 48px; color: #94a3b8; }
	.error { color: #dc2626; }
	.empty { text-align: center; padding: 64px; color: #94a3b8; }
	.empty code { background: #f4f4f5; padding: 2px 6px; border-radius: 3px; font-size: 12px; }

	.project-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
		gap: 10px;
	}

	.project-card {
		display: flex; flex-direction: column; gap: 10px;
		background: white; border: 1px solid #e8e5e0; border-radius: 12px;
		padding: 16px; text-decoration: none;
		transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
		cursor: pointer;
	}
	.project-card:hover {
		border-color: #3b82f6;
		box-shadow: 0 4px 16px rgba(59,130,246,0.08);
		transform: translateY(-1px);
	}

	.card-top { display: flex; align-items: center; justify-content: space-between; }
	.project-name { font-size: 14px; font-weight: 700; color: #232326; font-family: 'SF Mono', 'Fira Code', monospace; }
	.badge.insights { font-size: 9px; font-weight: 700; color: #16a34a; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; }

	.card-stats { display: flex; gap: 4px; }
	.stat { flex: 1; text-align: center; }
	.stat-val { display: block; font-size: 16px; font-weight: 800; color: #232326; letter-spacing: -0.5px; }
	.stat-label { display: block; font-size: 9px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }

	.card-tools { display: flex; gap: 4px; flex-wrap: wrap; }
	.tool-chip { font-size: 10px; font-family: monospace; background: #f4f4f5; color: #52525b; padding: 2px 7px; border-radius: 4px; }

	.card-footer { display: flex; align-items: center; justify-content: space-between; margin-top: auto; }
	.last-active { font-size: 11px; color: #a1a1aa; }
	.analyzed-badge { font-size: 10px; font-weight: 600; color: #6366f1; background: #eef2ff; padding: 2px 7px; border-radius: 4px; }

	.hover-panel {
		position: fixed; background: white; border: 1px solid #d4d4d8;
		border-radius: 14px; padding: 16px;
		box-shadow: 0 12px 40px rgba(0,0,0,0.15);
		z-index: 300; pointer-events: none;
	}
	.hp-name { font-size: 15px; font-weight: 700; color: #232326; font-family: monospace; margin-bottom: 10px; }
	.hp-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px; }
	.hp-item { text-align: center; padding: 3px 0; }
	.hp-val { display: block; font-size: 14px; font-weight: 700; color: #232326; }
	.hp-label { display: block; font-size: 8px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; }
	.hp-tools, .hp-langs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
	.hp-tool { font-size: 10px; font-weight: 600; font-family: monospace; color: #475569; background: #f1f5f9; padding: 2px 6px; border-radius: 3px; }
	.hp-lang { font-size: 10px; font-weight: 600; color: #2563eb; background: #eff6ff; padding: 2px 6px; border-radius: 3px; }
	.hp-digest { font-size: 10px; font-weight: 600; color: #16a34a; }
</style>
