<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getUsers, getDigests, getDigest, getUserMoodQuotes, getUserStats, type UserSummary, type UserMoodResponse } from '$lib/api';
	import type { SessionRead, DigestDetail, DigestStatsData } from '$lib/types';
	import { fmtTokens, avatarColor } from '$lib/format';
	import DashboardView from '$lib/components/DashboardView.svelte';
	import InsightsPanel from '$lib/components/InsightsPanel.svelte';
	import ActivityCharts from '$lib/components/ActivityCharts.svelte';
	import MoodQuotes from '$lib/components/MoodQuotes.svelte';
	import ExportHTML from '$lib/components/ExportHTML.svelte';
	import SessionTable from '$lib/components/SessionTable.svelte';

	const userId = $derived(decodeURIComponent(page.params.id ?? ''));

	let user: UserSummary | null = $state(null);
	let digest: DigestDetail | null = $state(null);
	let moodData: UserMoodResponse | null = $state(null);
	let scopeStats: DigestStatsData | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let expandedProjects: Set<string> = $state(new Set());
	let reportEl: HTMLElement = $state(null!);

	onMount(async () => {
		try {
			const [users, digests, mood, stats] = await Promise.all([
				getUsers(),
				getDigests(undefined, userId).catch(() => []),
				getUserMoodQuotes(userId).catch(() => null),
				getUserStats(userId).catch(() => null),
			]);
			user = users.find(u => u.user_id === userId) ?? null;
			if (!user) error = `User not found: ${userId}`;
			moodData = mood;
			if (stats && Object.keys(stats).length > 0) {
				scopeStats = stats as unknown as DigestStatsData;
			}

			const completed = digests.find(d => d.status === 'complete');
			if (completed) {
				digest = await getDigest(completed.id);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load user';
		} finally {
			loading = false;
		}
	});

	function toggleProject(name: string) {
		const next = new Set(expandedProjects);
		if (next.has(name)) next.delete(name); else next.add(name);
		expandedProjects = next;
	}

	function groupByProject(sessions: SessionRead[]): [string, SessionRead[]][] {
		const groups: Record<string, SessionRead[]> = {};
		for (const s of sessions) {
			(groups[s.project_name ?? 'Unknown'] ??= []).push(s);
		}
		return Object.entries(groups).sort(([, a], [, b]) => b.length - a.length);
	}
</script>

<svelte:head><title>{user?.display_name ?? 'User'} — cinsights</title></svelte:head>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="loading" style="color: #dc2626">{error}</div>
{:else if user}
	<div bind:this={reportEl}>
	<div class="user-banner">
		<span class="avatar-lg" style="background: {avatarColor(user.display_name)}">{user.display_name[0].toUpperCase()}</span>
		<div class="banner-info">
			<div class="banner-top">
				<h1>{user.display_name}</h1>
				<ExportHTML target={reportEl} filename="{user.display_name}-report" />
			</div>
			<p class="user-email">{user.user_id}</p>
			<div class="banner-tags">
				{#each user.agents as a}<span class="tag agent">{a}</span>{/each}
				{#each user.sources as s}<span class="tag source">{s}</span>{/each}
			</div>
		</div>
	</div>

	<DashboardView scope="user" {userId}>
		{#snippet extra({ sessions })}
			{@const sessionsByProject = groupByProject(sessions)}

			{#if sessionsByProject.length > 0}
				<div class="section">
					<h2>Sessions <span class="dim">({sessions.length} total)</span></h2>
					{#each sessionsByProject as [project, projectSessions]}
						{@const isOpen = expandedProjects.has(project)}
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
								<div class="project-table">
									<SessionTable sessions={projectSessions} compact />
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}

			{#if digest}
				<div class="section">
					<div class="insights-header">
						<h2>Insights</h2>
						<span class="insights-meta">
							{#if digest.analysis_model}<span class="model-badge">{digest.analysis_model}</span>{/if}
							<span class="generated-at">{new Date(digest.created_at).toLocaleDateString()}</span>
						</span>
					</div>
					<InsightsPanel {digest} moodGroups={moodData?.mood_groups ?? []} scopeStats={scopeStats ?? undefined} />
				</div>
			{:else}
				{@const stats = scopeStats}
				{#if stats}
					<div class="section">
						<h2>Activity</h2>
						<ActivityCharts
							toolDistribution={stats.tool_distribution ?? {}}
							languageDistribution={stats.language_distribution ?? {}}
							timeOfDay={stats.time_of_day ?? {}}
							errorTypes={stats.error_types ?? {}}
							insightLabels={stats.insight_labels ?? {}}
							labelCategories={stats.label_categories ?? {}}
							labelTrends={stats.label_trends ?? []}
							analyzedCount={stats.analyzed_count ?? 0}
							sessionCount={stats.session_count ?? 0}
							scopeUser={userId}
						/>
						<MoodQuotes moodGroups={moodData?.mood_groups ?? []} />
					</div>
				{/if}
				<div class="section">
					<div class="empty-insights">
						No report yet. Run <code>cinsights digest user {userId} --days 30</code> to generate.
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

	.user-banner { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
	.banner-info { flex: 1; }
	.avatar-lg { width: 52px; height: 52px; border-radius: 14px; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 24px; flex-shrink: 0; }
	.banner-top { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
	h1 { font-size: 24px; font-weight: 800; color: #232326; line-height: 1.2; }
	.user-email { font-size: 13px; color: #94a3b8; margin-bottom: 8px; }
	.banner-tags { display: flex; flex-wrap: wrap; gap: 4px; }
	.tag { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 5px; border: 1px solid; }
	.tag.agent { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
	.tag.source { background: #f0fdf4; color: #166534; border-color: #bbf7d0; }

	.section { margin-bottom: 28px; }
	h2 { font-size: 17px; font-weight: 700; color: #232326; margin-bottom: 12px; }
	.dim { font-size: 13px; font-weight: 400; color: #94a3b8; }

	.project-group { background: white; border: 1px solid #e8e5e0; border-radius: 10px; overflow: hidden; margin-bottom: 8px; }
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

	.project-table { border-top: 1px solid #e8e5e0; }
	.project-table :global(.table-wrap) { border: none; border-radius: 0; }

	.empty-insights { text-align: center; padding: 40px; color: #94a3b8; font-size: 14px; background: white; border-radius: 12px; }
	.empty-insights code { background: #f4f4f5; padding: 2px 8px; border-radius: 4px; font-size: 12px; }

</style>
