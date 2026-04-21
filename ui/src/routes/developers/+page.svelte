<script lang="ts">
	import { onMount } from 'svelte';
	import { getUsers, getDigests, type UserSummary } from '$lib/api';
	import type { DigestRead } from '$lib/types';
	import { fmtTokens, fmtDur, fmtNum, avatarColor } from '$lib/format';

	let users: UserSummary[] = $state([]);
	let loading = $state(true);
	let error: string | null = $state(null);
	let hoveredUser: UserSummary | null = $state(null);
	let hoverPos = $state({ x: 0, y: 0 });
	let usersWithDigest: Set<string> = $state(new Set());

	onMount(async () => {
		try {
			const [u, digests] = await Promise.all([
				getUsers(),
				getDigests().catch(() => [] as DigestRead[]),
			]);
			users = u;
			usersWithDigest = new Set(
				digests
					.filter(d => d.status === 'complete' && d.user_id)
					.map(d => d.user_id!)
			);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load developers';
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head>
	<title>Developers — cinsights</title>
</svelte:head>

<h1>Developers</h1>
<p class="subtitle">{users.length} developers tracked. Hover for details, click for full profile.</p>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="error">{error}</div>
{:else if users.length === 0}
	<div class="empty">
		<p>No developers found yet.</p>
		<p>Run <code>cinsights analyze</code> to index sessions and detect developers.</p>
	</div>
{:else}
	<div class="users-grid">
		{#each users as u}
			<a href="/users/{encodeURIComponent(u.user_id)}" class="user-card"
				onmouseenter={(e) => { hoveredUser = u; hoverPos = { x: e.clientX, y: e.clientY }; }}
				onmousemove={(e) => { hoverPos = { x: e.clientX, y: e.clientY }; }}
				onmouseleave={() => { hoveredUser = null; }}>
				<div class="card-header">
					<span class="avatar" style="background: {avatarColor(u.display_name)}">{u.display_name[0].toUpperCase()}</span>
					<div class="card-info">
						<div class="card-name">{u.display_name}</div>
						<div class="card-meta">{u.session_count} sessions · {u.projects.length} {u.projects.length === 1 ? 'project' : 'projects'}</div>
					</div>
					{#if usersWithDigest.has(u.user_id)}<span class="tag digest">report</span>{/if}
				</div>
				<div class="card-metrics">
					<div class="cm"><span class="cm-val">{fmtNum(u.avg_turn_count)}</span><span class="cm-label">Turns/s</span></div>
					<div class="cm"><span class="cm-val">{fmtDur(u.avg_duration_ms)}</span><span class="cm-label">Avg dur</span></div>
					<div class="cm"><span class="cm-val">{fmtTokens(Math.round(u.total_tokens / Math.max(u.session_count, 1)))}</span><span class="cm-label">Tok/s</span></div>
				</div>
				<div class="card-tags">
					{#each u.agents.slice(0, 2) as a}<span class="tag agent">{a}</span>{/each}
					{#if u.agents.length > 2}<span class="tag agent">+{u.agents.length - 2}</span>{/if}
					{#if u.analyzed_count > 0}<span class="tag analyzed">{u.analyzed_count} analyzed</span>{/if}
				</div>
			</a>
		{/each}
	</div>

	{#if hoveredUser}
		{@const u = hoveredUser}
		{@const panelW = 380}
		{@const panelH = 340}
		{@const px = Math.min(hoverPos.x + 16, (typeof window !== 'undefined' ? window.innerWidth : 1200) - panelW - 20)}
		{@const py = Math.min(hoverPos.y - panelH / 2, (typeof window !== 'undefined' ? window.innerHeight : 800) - panelH - 20)}
		<div class="hover-panel" style="left: {Math.max(8, px)}px; top: {Math.max(8, py)}px">
			<div class="hp-header">
				<span class="avatar" style="background: {avatarColor(u.display_name)}">{u.display_name[0].toUpperCase()}</span>
				<div>
					<div class="hp-name">{u.display_name}</div>
					<div class="hp-email">{u.user_id}</div>
				</div>
			</div>
			<div class="hp-tags">
				{#each u.projects as p}<span class="hp-tag project">{p}</span>{/each}
				{#each u.agents as a}<span class="hp-tag agent">{a}</span>{/each}
				{#each u.sources as s}<span class="hp-tag source">{s}</span>{/each}
			</div>
			<div class="hp-grid">
				<div class="hp-item"><span class="hp-val">{u.session_count}</span><span class="hp-label">Sessions</span></div>
				<div class="hp-item"><span class="hp-val">{u.analyzed_count}</span><span class="hp-label">Analyzed</span></div>
				<div class="hp-item"><span class="hp-val">{fmtTokens(u.total_tokens)}</span><span class="hp-label">Tokens</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_read_edit_ratio)}</span><span class="hp-label">Read:Edit</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_edits_without_read_pct, '%')}</span><span class="hp-label">Blind edits</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_research_mutation_ratio)}</span><span class="hp-label">Research:Mut</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_write_vs_edit_pct, '%')}</span><span class="hp-label">Write vs Edit</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_error_rate, '%')}</span><span class="hp-label">Error rate</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_repeated_edits)}</span><span class="hp-label">Thrashing</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_subagent_spawn_rate, '%')}</span><span class="hp-label">Subagents</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_context_pressure)}</span><span class="hp-label">Ctx pressure</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_tool_calls_per_turn)}</span><span class="hp-label">Tools/turn</span></div>
				<div class="hp-item"><span class="hp-val">{fmtNum(u.avg_turn_count)}</span><span class="hp-label">Turns/sess</span></div>
				<div class="hp-item"><span class="hp-val">{fmtDur(u.avg_duration_ms)}</span><span class="hp-label">Avg duration</span></div>
			</div>
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

	.users-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }

	.user-card {
		background: white; border: 1px solid #e8e5e0; border-radius: 12px;
		padding: 14px; text-decoration: none; display: flex; flex-direction: column; gap: 10px;
		transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s; cursor: pointer;
	}
	.user-card:hover {
		border-color: #3b82f6;
		box-shadow: 0 4px 16px rgba(59,130,246,0.08);
		transform: translateY(-1px);
	}

	.card-header { display: flex; align-items: center; gap: 10px; position: relative; }
	.avatar { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 15px; flex-shrink: 0; }
	.card-name { font-size: 14px; font-weight: 600; color: #232326; }
	.card-meta { font-size: 11px; color: #a1a1aa; }

	.card-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; }
	.cm { text-align: center; }
	.cm-val { display: block; font-size: 15px; font-weight: 700; color: #232326; }
	.cm-label { display: block; font-size: 9px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }

	.card-tags { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
	.tag.analyzed { margin-left: auto; }
	.tag { font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 4px; }
	.tag.agent { background: #fef3c7; color: #92400e; }
	.tag.analyzed { background: #eef2ff; color: #6366f1; }
	.tag.digest { background: #f0fdf4; color: #16a34a; margin-left: auto; }

	.hover-panel {
		position: fixed; width: 380px; background: white; border: 1px solid #d4d4d8;
		border-radius: 14px; padding: 16px;
		box-shadow: 0 12px 40px rgba(0,0,0,0.15);
		z-index: 300; pointer-events: none;
	}
	.hp-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
	.hp-name { font-size: 15px; font-weight: 700; color: #232326; }
	.hp-email { font-size: 11px; color: #a1a1aa; }
	.hp-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
	.hp-tag { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; border: 1px solid; }
	.hp-tag.project { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }
	.hp-tag.agent { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
	.hp-tag.source { background: #f0fdf4; color: #166534; border-color: #bbf7d0; }
	.hp-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
	.hp-item { text-align: center; padding: 3px 0; }
	.hp-val { display: block; font-size: 14px; font-weight: 700; color: #232326; }
	.hp-label { display: block; font-size: 8px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; }
</style>
