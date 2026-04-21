<script lang="ts">
	import type { Snippet } from 'svelte';
	import { onMount } from 'svelte';
	import { getStats, getTrends, getUsers, getProjects, getSessions, getTokenDistribution, type TrendPoint, type UserSummary, type ProjectRead, type TokenDistribution } from '$lib/api';
	import type { StatsResponse, SessionRead } from '$lib/types';
	import { fmtTokens, userQualityMetrics, aggregateQualityMetrics, type QualityMetric } from '$lib/format';
	import QualityBar from './QualityBar.svelte';
	import HeroMetrics from './HeroMetrics.svelte';
	import TrendCharts from './TrendCharts.svelte';

	let {
		scope,
		userId = undefined,
		projectName = undefined,
		extra = undefined,
	}: {
		scope: 'org' | 'user' | 'project';
		userId?: string;
		projectName?: string;
		extra?: Snippet<[{ users: UserSummary[]; sessions: SessionRead[]; projects: ProjectRead[] }]>;
	} = $props();

	let stats: StatsResponse | null = $state(null);
	let trends: TrendPoint[] = $state([]);
	let users: UserSummary[] = $state([]);
	let projects: ProjectRead[] = $state([]);
	let sessions: SessionRead[] = $state([]);
	let tokenDist: TokenDistribution | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);

	onMount(async () => {
		try {
			const promises: Promise<unknown>[] = [
				getTrends(projectName, userId),
				getTokenDistribution(projectName, userId),
				getUsers(undefined, undefined, projectName),
			];
			if (scope === 'org') {
				promises.push(getStats(), getProjects());
			}
			if (scope === 'user' || scope === 'project') {
				promises.push(getSessions(0, 500, undefined, userId, projectName));
			}

			const results = await Promise.all(promises);
			trends = results[0] as TrendPoint[];
			tokenDist = results[1] as TokenDistribution | null;
			users = results[2] as UserSummary[];

			if (scope === 'org') {
				stats = results[3] as StatsResponse;
				projects = results[4] as ProjectRead[];
			}
			if (scope === 'user' || scope === 'project') {
				sessions = results[3] as SessionRead[];
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load dashboard';
		} finally {
			loading = false;
		}
	});

	const daysTracked = $derived(new Set(trends.map(t => t.date)).size);
	const totalTokens = $derived(trends.reduce((s, t) => s + t.total_tokens, 0));
	const latestDate = $derived(trends.length ? trends[trends.length - 1].date : '-');

	const matchedUser = $derived(scope === 'user' ? users.find(u => u.user_id === userId) ?? null : null);

	const teamAvgs = $derived.by<Record<string, number | null>>(() => {
		if (scope !== 'user' || users.length < 2) return {};
		const keys = ['avg_read_edit_ratio', 'avg_edits_without_read_pct', 'avg_research_mutation_ratio', 'avg_error_rate', 'avg_write_vs_edit_pct', 'avg_repeated_edits', 'avg_subagent_spawn_rate', 'avg_context_pressure', 'avg_tool_calls_per_turn', 'avg_duration_ms'];
		const result: Record<string, number | null> = {};
		for (const k of keys) {
			const vals = users.map(u => (u as unknown as Record<string, unknown>)[k] as number | null).filter((v): v is number => v != null);
			result[k] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
		}
		return result;
	});

	const qualityMetrics = $derived<QualityMetric[]>(
		scope === 'user' && matchedUser
			? userQualityMetrics(matchedUser as unknown as Record<string, unknown>, Object.keys(teamAvgs).length > 0 ? teamAvgs : undefined)
			: aggregateQualityMetrics(users as unknown as Record<string, unknown>[])
	);

	const heroMetrics = $derived.by(() => {
		if (scope === 'org') {
			return [
				{ value: String(stats?.total_sessions ?? 0), label: 'Sessions', sub: `${stats?.analyzed_sessions ?? 0} analyzed · ${(stats?.total_sessions ?? 0) - (stats?.analyzed_sessions ?? 0)} indexed` },
				{ value: fmtTokens(totalTokens), label: 'Total Tokens', sub: 'across all sessions' },
				{ value: String(users.length), label: 'Developers', sub: `${projects.length} projects` },
				{ value: String(daysTracked), label: 'Days Tracked', sub: `${latestDate.slice(5)} latest` },
			];
		}
		if (scope === 'user' && matchedUser) {
			return [
				{ value: String(matchedUser.session_count), label: 'Sessions', sub: `${matchedUser.analyzed_count} analyzed · ${matchedUser.indexed_count} indexed` },
				{ value: fmtTokens(totalTokens), label: 'Total Tokens', sub: 'across all sessions' },
				{ value: String(matchedUser.projects.length), label: 'Projects', sub: matchedUser.projects.slice(0, 3).join(', ') || 'none' },
				{ value: String(daysTracked), label: 'Days Active', sub: matchedUser.agents.join(', ') },
			];
		}
		// project scope
		return [
			{ value: String(sessions.length), label: 'Sessions', sub: 'in this project' },
			{ value: fmtTokens(totalTokens), label: 'Total Tokens', sub: 'across all sessions' },
			{ value: String(users.length), label: 'Developers', sub: users.slice(0, 3).map(u => u.display_name).join(', ') || '-' },
			{ value: String(daysTracked), label: 'Days Active', sub: `${latestDate.slice(5)} latest` },
		];
	});
</script>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="loading" style="color: #dc2626">{error}</div>
{:else}
	<HeroMetrics metrics={heroMetrics} />

	{#if qualityMetrics.length > 0}
		<QualityBar metrics={qualityMetrics} />
	{/if}

	<TrendCharts {trends} {tokenDist} />

	{#if extra}
		{@render extra({ users, sessions, projects })}
	{/if}
{/if}

<style>
	.loading { text-align: center; padding: 80px; color: #94a3b8; }
</style>
