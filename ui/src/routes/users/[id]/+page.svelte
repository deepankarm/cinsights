<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getUsers, getDigests, getDigest, getUserMoodQuotes, type UserSummary, type UserMoodResponse } from '$lib/api';
	import type { SessionRead, DigestDetail } from '$lib/types';
	import { fmtTokens, avatarColor } from '$lib/format';
	import DashboardView from '$lib/components/DashboardView.svelte';
	import InsightsPanel from '$lib/components/InsightsPanel.svelte';
	import ExportHTML from '$lib/components/ExportHTML.svelte';
	import SessionTable from '$lib/components/SessionTable.svelte';

	const userId = $derived(decodeURIComponent(page.params.id ?? ''));

	let user: UserSummary | null = $state(null);
	let digest: DigestDetail | null = $state(null);
	let moodData: UserMoodResponse | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let expandedProjects: Set<string> = $state(new Set());
	let expandedMoods: Set<string> = $state(new Set());
	let reportEl: HTMLElement = $state(null!);

	const MOOD_META: Record<string, { icon: string; color: string; bg: string; label: string }> = {
		frustrated: { icon: '😤', color: '#dc2626', bg: '#fef2f2', label: 'Frustrated' },
		curious:    { icon: '🤔', color: '#2563eb', bg: '#eff6ff', label: 'Curious' },
		amused:     { icon: '😄', color: '#ca8a04', bg: '#fefce8', label: 'Amused' },
		relieved:   { icon: '😮‍💨', color: '#16a34a', bg: '#f0fdf4', label: 'Relieved' },
		assertive:  { icon: '✋', color: '#7c3aed', bg: '#f5f3ff', label: 'Assertive' },
	};

	function toggleMood(mood: string) {
		const next = new Set(expandedMoods);
		if (next.has(mood)) next.delete(mood); else next.add(mood);
		expandedMoods = next;
	}

	onMount(async () => {
		try {
			const [users, digests, mood] = await Promise.all([
				getUsers(),
				getDigests(undefined, userId).catch(() => []),
				getUserMoodQuotes(userId).catch(() => null),
			]);
			user = users.find(u => u.user_id === userId) ?? null;
			if (!user) error = `User not found: ${userId}`;
			moodData = mood;

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
					<InsightsPanel {digest} />
				</div>
			{:else}
				<div class="section">
					<div class="empty-insights">
						No insights yet. Run <code>cinsights digest user {userId} --days 30</code> to generate.
					</div>
				</div>
			{/if}

			{#if moodData && moodData.mood_groups.length > 0}
				<div class="section">
					<h2>Things you've said <span class="dim">across {moodData.sessions_with_quotes} sessions</span></h2>
					<div class="mood-feed">
						{#each moodData.mood_groups as group}
							{@const meta = MOOD_META[group.mood] ?? { icon: '💬', color: '#64748b', bg: '#f8fafc', label: group.mood }}
							{@const isOpen = expandedMoods.has(group.mood)}
							{@const visible = isOpen ? group.quotes : group.quotes.slice(0, 3)}
							{@const hidden = group.quotes.length - 3}
							<div class="mood-row">
								<div class="mood-tag" style="color: {meta.color}">
									<span class="mood-icon">{meta.icon}</span>
									<span class="mood-name">{meta.label}</span>
									<span class="mood-cnt" style="background: {meta.bg}">{group.quotes.length}</span>
								</div>
								<div class="mood-quotes-list">
									{#each visible as q}
										<div class="mq">&ldquo;{q.quote.length > 100 ? q.quote.slice(0, 100) + '...' : q.quote}&rdquo;</div>
									{/each}
									{#if !isOpen && hidden > 0}
										<button class="mq-more" onclick={() => toggleMood(group.mood)}>+{hidden} more</button>
									{/if}
									{#if isOpen && group.quotes.length > 3}
										<button class="mq-more" onclick={() => toggleMood(group.mood)}>show less</button>
									{/if}
								</div>
							</div>
						{/each}
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

	/* Mood quotes */
	.mood-feed { background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 4px 0; }
	.mood-row { display: flex; gap: 12px; padding: 10px 16px; border-bottom: 1px solid #f4f4f5; align-items: baseline; }
	.mood-row:last-child { border-bottom: none; }
	.mood-tag { display: flex; align-items: center; gap: 5px; flex-shrink: 0; min-width: 110px; }
	.mood-icon { font-size: 16px; }
	.mood-name { font-size: 12px; font-weight: 700; }
	.mood-cnt { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 8px; }
	.mood-quotes-list { display: flex; flex-direction: column; gap: 4px; }
	.mq { font-size: 13px; color: #475569; font-style: italic; line-height: 1.4; }
	.mq-more { background: none; border: none; font-size: 12px; color: #6366f1; cursor: pointer; font-weight: 600; margin-left: 4px; }
	.mq-more:hover { text-decoration: underline; }
</style>
