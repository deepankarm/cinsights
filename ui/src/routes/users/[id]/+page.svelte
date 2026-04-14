<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getUsers, getDigests, getDigest, type UserSummary } from '$lib/api';
	import type { SessionRead, DigestDetail } from '$lib/types';
	import { fmtTokens, fmtDate, fmtDuration, avatarColor } from '$lib/format';
	import DashboardView from '$lib/components/DashboardView.svelte';
	import InsightsPanel from '$lib/components/InsightsPanel.svelte';
	import ExportHTML from '$lib/components/ExportHTML.svelte';

	const userId = $derived(decodeURIComponent(page.params.id));

	let user: UserSummary | null = $state(null);
	let digest: DigestDetail | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let expandedProjects: Set<string> = $state(new Set());
	let reportEl: HTMLElement = $state(null!);

	onMount(async () => {
		try {
			const [users, digests] = await Promise.all([
				getUsers(),
				getDigests(undefined, userId).catch(() => []),
			]);
			user = users.find(u => u.user_id === userId) ?? null;
			if (!user) error = `User not found: ${userId}`;

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

			{#if digest}
				<div class="section">
					<h2>Insights</h2>
					<InsightsPanel {digest} />
				</div>
			{:else}
				<div class="section">
					<div class="empty-insights">
						No insights yet. Run <code>cinsights digest user {userId} --days 30</code> to generate.
					</div>
				</div>
			{/if}
		{/snippet}
	</DashboardView>
	</div>
{/if}

<style>
	.loading { text-align: center; padding: 80px; color: #94a3b8; }

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
	.empty-insights { text-align: center; padding: 40px; color: #94a3b8; font-size: 14px; background: white; border-radius: 12px; }
	.empty-insights code { background: #f4f4f5; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
</style>
