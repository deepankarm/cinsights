<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getProjects, getDigests, getDigest, getProjectStats, getProjectThemes, type ProjectRead } from '$lib/api';
	import type { SessionRead, DigestDetail, DigestStatsData, ThemeRead } from '$lib/types';
	import { fmtTokens, fmtDate, fmtDateRange, fmtDuration } from '$lib/format';
	import DashboardView from '$lib/components/DashboardView.svelte';
	import InsightsPanel from '$lib/components/InsightsPanel.svelte';
	import ActivityCharts from '$lib/components/ActivityCharts.svelte';
	import ExportHTML from '$lib/components/ExportHTML.svelte';
	import ThemeSwimlane from '$lib/components/ThemeSwimlane.svelte';

	const projectName = $derived(decodeURIComponent(page.params.name ?? ''));

	let project: ProjectRead | null = $state(null);
	let digest: DigestDetail | null = $state(null);
	let scopeStats: DigestStatsData | null = $state(null);
	let themes: ThemeRead[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);
	let expandedUsers: Set<string> = $state(new Set());
	let reportEl: HTMLElement = $state(null!);
	let showAllUsers = $state(false);

	onMount(async () => {
		try {
			const [projects, digests, stats, projectThemes] = await Promise.all([
				getProjects(),
				getDigests(projectName).catch(() => []),
				getProjectStats(projectName).catch(() => null),
				getProjectThemes(projectName).catch(() => []),
			]);
			project = projects.find(p => p.name === projectName) ?? null;
			if (!project) error = `Project not found: ${projectName}`;
			if (stats) scopeStats = stats as unknown as DigestStatsData;
			themes = projectThemes;

			const completed = digests.find(d => d.status === 'complete');
			if (completed) {
				digest = await getDigest(completed.id);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load project';
		} finally {
			loading = false;
		}
	});

	function toggleUser(name: string) {
		const next = new Set(expandedUsers);
		if (next.has(name)) next.delete(name); else next.add(name);
		expandedUsers = next;
	}

	function displayId(id: string): string {
		if (id.startsWith('local:')) return id.split(':').slice(2).join(':').slice(0, 16);
		if (id.startsWith('entireio:')) return id.split(':')[1].slice(0, 8);
		return id.slice(0, 8);
	}
	function statColor(s: string): string {
		return s === 'analyzed' ? '#16a34a' : s === 'indexed' ? '#8b5cf6' : '#64748b';
	}
	function statIcon(s: string): string {
		return s === 'analyzed' ? '●' : s === 'indexed' ? '○' : s === 'failed' ? '✗' : '·';
	}

	function groupByUser(sessions: SessionRead[]): [string, SessionRead[]][] {
		const groups: Record<string, SessionRead[]> = {};
		for (const s of sessions) {
			(groups[s.user_id ?? 'Unknown'] ??= []).push(s);
		}
		return Object.entries(groups).sort(([, a], [, b]) => b.length - a.length);
	}
</script>

<svelte:head><title>{projectName} — cinsights</title></svelte:head>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="loading" style="color: #dc2626">{error}</div>
{:else if project}
	<div bind:this={reportEl}>
	<div class="project-banner">
		<div class="banner-info">
			<div class="banner-top">
				<h1>{project.name}</h1>
				<ExportHTML target={reportEl} filename="{project.name}-report" />
			</div>
			<div class="banner-meta">
				<span>{project.session_count} sessions</span>
				<span>{project.total_tool_calls.toLocaleString()} tool calls</span>
				<span>{fmtTokens(project.total_tokens)} tokens</span>
			</div>
			<div class="banner-tags">
				{#each project.top_tools.slice(0, 5) as t}<span class="tag tool">{t}</span>{/each}
				{#each project.languages as l}<span class="tag lang">{l}</span>{/each}
				{#if digest}
					<span class="tag insights">Insights</span>
				{/if}
			</div>
		</div>
	</div>

	<DashboardView scope="project" {projectName}>
		{#snippet extra({ sessions })}
			{@const sessionsByUser = groupByUser(sessions)}
			{@const userLimit = 5}
			{@const visibleUsers = showAllUsers ? sessionsByUser : sessionsByUser.slice(0, userLimit)}
			{#if sessionsByUser.length > 0}
				<div class="section">
					<h2>Sessions <span class="dim">({project?.session_count ?? sessions.length} total, {project?.developer_count ?? sessionsByUser.length} developers)</span></h2>
					<div class="user-list">
						{#each visibleUsers as [userId, userSessions]}
							{@const isOpen = expandedUsers.has(userId)}
							{@const preview = userSessions.slice(0, 5)}
							{@const analyzed = userSessions.filter(s => s.status === 'analyzed').length}
							<div class="user-group">
								<button class="user-header" onclick={() => toggleUser(userId)}>
									<span class="uh-arrow">{isOpen ? '▾' : '▸'}</span>
									<span class="uh-name">{userId}</span>
									<span class="uh-count">{userSessions.length} sessions</span>
									{#if analyzed > 0}
										<span class="uh-analyzed">{analyzed} analyzed</span>
									{/if}
									<span class="uh-tokens">{fmtTokens(userSessions.reduce((s, x) => s + x.total_tokens, 0))}</span>
								</button>
								{#if isOpen}
									<div class="user-sessions">
										{#each userSessions as s}
											<a href="/sessions/{s.id}" class="session-row">
												<span class="sr-id">{displayId(s.id)}</span>
												<span class="sr-time">{fmtDateRange(s.start_time, s.end_time)}</span>
												<span class="sr-dur">{fmtDuration(s.start_time, s.end_time)}</span>
												<span class="sr-tools">{s.tool_call_count || '-'} tools</span>
												<span class="sr-tokens">{fmtTokens(s.total_tokens)}</span>
												<span class="sr-status" style="color: {statColor(s.status)}">{statIcon(s.status)} {s.status}</span>
											</a>
										{/each}
									</div>
								{:else}
									<div class="user-preview">
										{#each preview as s}
											<a href="/sessions/{s.id}" class="preview-chip">
												<span class="pc-id">{displayId(s.id)}</span>
												<span class="pc-dur">{fmtDuration(s.start_time, s.end_time)}</span>
												<span class="pc-status" style="color: {statColor(s.status)}">{statIcon(s.status)}</span>
											</a>
										{/each}
										{#if userSessions.length > 5}
											<button class="preview-more" onclick={() => toggleUser(userId)}>+{userSessions.length - 5} more</button>
										{/if}
									</div>
								{/if}
							</div>
						{/each}
					</div>
					{#if sessionsByUser.length > userLimit}
						<button class="show-more" onclick={() => showAllUsers = !showAllUsers}>
							{showAllUsers ? 'Show fewer' : `Show all ${sessionsByUser.length} developers`}
						</button>
					{/if}
				</div>
			{/if}

			<!-- Themes -->
			{#if themes.length > 0}
				<div class="section">
					<h2>Themes <span class="dim">({themes.length} work areas)</span></h2>
					<ThemeSwimlane {themes} />
				</div>
			{/if}

			<!-- Insights -->
			{#if digest}
				<div class="section">
					<div class="insights-header">
						<h2>Insights</h2>
						<span class="insights-meta">
							{#if digest.analysis_model}<span class="model-badge">{digest.analysis_model}</span>{/if}
							<span class="generated-at">{new Date(digest.created_at).toLocaleDateString()}</span>
						</span>
					</div>
					<InsightsPanel {digest} scopeStats={scopeStats ?? undefined} />
				</div>
			{:else if scopeStats}
				<div class="section">
					<h2>Activity</h2>
					<ActivityCharts
						toolDistribution={scopeStats.tool_distribution}
						languageDistribution={scopeStats.language_distribution}
						timeOfDay={scopeStats.time_of_day}
						errorTypes={scopeStats.error_types}
						sessionCount={scopeStats.session_count}
						analyzedCount={scopeStats.analyzed_count}
					/>
					<div class="empty-insights" style="margin-top: 16px">
						Run <code>cinsights digest project {projectName} --days 30</code> to generate insights.
					</div>
				</div>
			{:else}
				<div class="section">
					<div class="empty-insights">
						No insights yet. Run <code>cinsights digest project {projectName} --days 30</code> to generate.
					</div>
				</div>
			{/if}
		{/snippet}
	</DashboardView>
	</div>
{/if}

<style>
	.loading { text-align: center; padding: 80px; color: #94a3b8; }
	.insights-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: -8px; }
	.insights-meta { display: flex; align-items: center; gap: 8px; }
	.model-badge { font-size: 11px; font-weight: 600; color: #6366f1; background: #eef2ff; border: 1px solid #c7d2fe; padding: 2px 8px; border-radius: 4px; font-family: monospace; }
	.generated-at { font-size: 12px; color: #94a3b8; }

	.project-banner { margin-bottom: 20px; }
	.banner-info { flex: 1; }
	.banner-top { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
	h1 { font-size: 24px; font-weight: 800; color: #232326; line-height: 1.2; font-family: monospace; }
	.banner-meta { display: flex; gap: 16px; font-size: 13px; color: #64748b; margin: 6px 0 10px; }
	.banner-tags { display: flex; flex-wrap: wrap; gap: 4px; }
	.tag { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 5px; border: 1px solid; text-decoration: none; }
	.tag.tool { background: #f1f5f9; color: #475569; border-color: #e2e8f0; font-family: monospace; }
	.tag.lang { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }
	.tag.insights { background: #f0fdf4; color: #16a34a; border-color: #bbf7d0; }
	.empty-insights { text-align: center; padding: 40px; color: #94a3b8; font-size: 14px; background: white; border-radius: 12px; }
	.empty-insights code { background: #f4f4f5; padding: 2px 8px; border-radius: 4px; font-size: 12px; }

	.section { margin-bottom: 28px; }
	h2 { font-size: 17px; font-weight: 700; color: #232326; margin-bottom: 12px; }
	.dim { font-size: 13px; font-weight: 400; color: #94a3b8; }

	.user-list { display: flex; flex-direction: column; gap: 8px; }
	.user-group { background: white; border: 1px solid #e8e5e0; border-radius: 10px; overflow: hidden; }
	.user-header {
		display: flex; align-items: center; gap: 10px; width: 100%; padding: 12px 16px;
		background: none; border: none; cursor: pointer; text-align: left;
		font-size: 14px; transition: background 0.1s;
	}
	.user-header:hover { background: #f8fafc; }
	.uh-arrow { font-size: 12px; color: #94a3b8; width: 16px; }
	.uh-name { font-weight: 700; color: #232326; }
	.uh-count { font-size: 12px; color: #64748b; }
	.uh-analyzed { font-size: 11px; color: #16a34a; background: #f0fdf4; padding: 1px 6px; border-radius: 3px; }
	.uh-tokens { font-size: 12px; color: #94a3b8; margin-left: auto; font-family: monospace; }

	.user-preview { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 16px 12px; }
	.preview-chip {
		display: flex; align-items: center; gap: 6px; padding: 3px 10px;
		background: #f8fafc; border-radius: 5px; font-size: 11px; text-decoration: none; color: #475569;
		transition: background 0.1s;
	}
	.preview-chip:hover { background: #eff6ff; }
	.pc-id { font-family: monospace; color: #2563eb; font-weight: 500; }
	.pc-dur { color: #94a3b8; }
	.preview-more { background: none; border: 1px dashed #d4d4d8; border-radius: 5px; padding: 3px 10px; font-size: 11px; color: #3b82f6; cursor: pointer; }
	.show-more { display: block; margin: 16px auto 0; background: white; border: none; border-radius: 10px; padding: 10px 24px; font-size: 13px; font-weight: 500; color: #70707a; cursor: pointer; transition: all 0.15s; }
	.show-more:hover { color: #232326; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }

	.user-sessions { border-top: 1px solid #f1f5f9; }
	.session-row {
		display: grid; grid-template-columns: 140px 100px 70px 70px 70px 90px;
		gap: 8px; padding: 8px 16px; text-decoration: none; font-size: 12px; color: #334155;
		border-bottom: 1px solid #f8fafc; align-items: center; transition: background 0.1s;
	}
	.session-row:last-child { border-bottom: none; }
	.session-row:hover { background: #f8fafc; }
	.sr-id { font-family: monospace; color: #2563eb; font-weight: 500; }
	.sr-time { color: #64748b; }
	.sr-dur { font-family: monospace; color: #475569; }
	.sr-tools { color: #64748b; }
	.sr-tokens { font-family: monospace; color: #475569; text-align: right; }
	.sr-status { font-size: 11px; text-align: right; }
</style>
