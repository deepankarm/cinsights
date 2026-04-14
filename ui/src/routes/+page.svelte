<script lang="ts">
	import type { UserSummary, ProjectRead } from '$lib/api';
	import { fmtTokens, fmtDur, fmtNum, avatarColor } from '$lib/format';
	import DashboardView from '$lib/components/DashboardView.svelte';

	let hoveredUser: UserSummary | null = $state(null);
	let hoveredProject: ProjectRead | null = $state(null);
	let hoverPos = $state({ x: 0, y: 0 });
</script>

<svelte:head><title>cinsights</title></svelte:head>

<DashboardView scope="org">
	{#snippet extra({ users, projects })}
		{#if users.length > 0}
			<div class="section">
				<h2>Developers</h2>
				<p class="section-desc">{users.length} developers across {projects.length} projects. Hover for details.</p>
				<div class="users-grid">
					{#each users as u}
						<a href="/users/{encodeURIComponent(u.user_id)}" class="user-card"
							onmouseenter={(e) => { hoveredUser = u; hoverPos = { x: e.clientX, y: e.clientY }; }}
							onmousemove={(e) => { hoverPos = { x: e.clientX, y: e.clientY }; }}
							onmouseleave={() => { hoveredUser = null; }}>
							<div class="user-header">
								<span class="avatar" style="background: {avatarColor(u.display_name)}">{u.display_name[0].toUpperCase()}</span>
								<div class="user-info">
									<div class="user-name">{u.display_name}</div>
									<div class="user-meta">{u.session_count} sessions · {u.agents.join(', ')}</div>
								</div>
							</div>
							<div class="user-metrics">
								<div class="um"><span class="um-val">{fmtNum(u.avg_read_edit_ratio)}</span><span class="um-label">R:E</span></div>
								<div class="um"><span class="um-val">{fmtNum(u.avg_error_rate, '%')}</span><span class="um-label">Errors</span></div>
								<div class="um"><span class="um-val">{fmtNum(u.avg_turn_count)}</span><span class="um-label">Turns/s</span></div>
								<div class="um"><span class="um-val">{fmtDur(u.avg_duration_ms)}</span><span class="um-label">Avg dur</span></div>
							</div>
						</a>
					{/each}
				</div>
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

		{#if projects.length > 0}
			<div class="section">
				<h2>Projects</h2>
				<p class="section-desc">{projects.length} projects. Hover for details.</p>
				<div class="project-cards">
					{#each projects as p}
						<a href="/projects/{encodeURIComponent(p.name)}" class="project-card"
							onmouseenter={(e) => { hoveredProject = p; hoverPos = { x: e.clientX, y: e.clientY }; }}
							onmousemove={(e) => { hoverPos = { x: e.clientX, y: e.clientY }; }}
							onmouseleave={() => { hoveredProject = null; }}>
							<div class="pc-top">
								<div class="pc-name">{p.name}</div>
								{#if p.has_digest}<span class="pc-badge">Insights</span>{/if}
							</div>
							<div class="pc-stats">
								<div class="pc-stat">
									<span class="pc-val">{p.session_count}</span>
									<span class="pc-label">sessions</span>
								</div>
								<div class="pc-stat">
									<span class="pc-val">{p.developer_count}</span>
									<span class="pc-label">{p.developer_count === 1 ? 'dev' : 'devs'}</span>
								</div>
								<div class="pc-stat">
									<span class="pc-val">{fmtTokens(p.total_tokens)}</span>
									<span class="pc-label">tokens</span>
								</div>
							</div>
							<div class="pc-footer">
								{#if p.analyzed_count > 0}
									<span class="pc-analyzed">{p.analyzed_count} analyzed</span>
								{/if}
							</div>
						</a>
					{/each}
				</div>
			</div>

			{#if hoveredProject}
				{@const p = hoveredProject}
				{@const panelW = 300}
				{@const panelH = 200}
				{@const px = Math.min(hoverPos.x + 16, (typeof window !== 'undefined' ? window.innerWidth : 1200) - panelW - 20)}
				{@const py = Math.min(hoverPos.y - panelH / 2, (typeof window !== 'undefined' ? window.innerHeight : 800) - panelH - 20)}
				<div class="hover-panel proj-panel" style="left: {Math.max(8, px)}px; top: {Math.max(8, py)}px; width: {panelW}px">
					<div class="pp-name">{p.name}</div>
					<div class="pp-grid">
						<div class="pp-item"><span class="pp-val">{p.session_count}</span><span class="pp-label">Sessions</span></div>
						<div class="pp-item"><span class="pp-val">{p.analyzed_count}</span><span class="pp-label">Analyzed</span></div>
						<div class="pp-item"><span class="pp-val">{p.session_count - p.analyzed_count}</span><span class="pp-label">Indexed</span></div>
						<div class="pp-item"><span class="pp-val">{p.developer_count}</span><span class="pp-label">Developers</span></div>
						<div class="pp-item"><span class="pp-val">{p.active_days}</span><span class="pp-label">Active days</span></div>
						<div class="pp-item"><span class="pp-val">{fmtTokens(p.total_tokens)}</span><span class="pp-label">Tokens</span></div>
					</div>
					{#if p.top_tools.length > 0}
						<div class="pp-tools">
							{#each p.top_tools as t}<span class="pp-tool">{t}</span>{/each}
						</div>
					{/if}
					{#if p.has_digest}<div class="pp-digest">Insights available</div>{/if}
				</div>
			{/if}
		{/if}
	{/snippet}
</DashboardView>

<style>
	.section { margin-bottom: 28px; }
	h2 { font-size: 17px; font-weight: 700; color: #232326; margin-bottom: 2px; }
	.section-desc { font-size: 12px; color: #a1a1aa; margin-bottom: 14px; }

	.users-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
	.user-card { background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 14px; text-decoration: none; transition: border-color 0.15s, box-shadow 0.15s; cursor: pointer; }
	.user-card:hover { border-color: #3b82f6; box-shadow: 0 2px 8px rgba(59,130,246,0.08); }
	.user-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
	.avatar { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 15px; flex-shrink: 0; }
	.user-name { font-size: 14px; font-weight: 600; color: #232326; }
	.user-meta { font-size: 11px; color: #a1a1aa; }
	.user-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
	.um { text-align: center; }
	.um-val { display: block; font-size: 15px; font-weight: 700; color: #232326; }
	.um-label { display: block; font-size: 9px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }

	.hover-panel { position: fixed; width: 380px; background: white; border: 1px solid #d4d4d8; border-radius: 14px; padding: 16px; box-shadow: 0 12px 40px rgba(0,0,0,0.15); z-index: 300; pointer-events: none; }
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

	.project-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
	.project-card {
		display: flex; flex-direction: column; background: white; border: 1px solid #e8e5e0;
		border-radius: 12px; padding: 16px; text-decoration: none;
		transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s; min-height: 120px;
	}
	.project-card:hover { border-color: #3b82f6; box-shadow: 0 4px 16px rgba(59,130,246,0.08); transform: translateY(-1px); }
	.pc-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
	.pc-name { font-size: 14px; font-weight: 700; color: #232326; font-family: 'SF Mono', 'Fira Code', monospace; }
	.pc-badge { font-size: 9px; font-weight: 700; color: #16a34a; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; }
	.pc-stats { display: flex; gap: 4px; margin-bottom: auto; }
	.pc-stat { flex: 1; text-align: center; }
	.pc-val { display: block; font-size: 16px; font-weight: 800; color: #232326; letter-spacing: -0.5px; }
	.pc-label { display: block; font-size: 9px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }
	.pc-footer { display: flex; gap: 6px; margin-top: 12px; flex-wrap: wrap; }
	.pc-analyzed { font-size: 10px; font-weight: 600; color: #6366f1; background: #eef2ff; padding: 2px 7px; border-radius: 4px; }
	.pc-insights { font-size: 10px; font-weight: 600; color: #16a34a; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 2px 6px; border-radius: 4px; }

	.proj-panel { }
	.pp-name { font-size: 15px; font-weight: 700; color: #232326; font-family: monospace; margin-bottom: 10px; }
	.pp-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px; }
	.pp-item { text-align: center; padding: 3px 0; }
	.pp-val { display: block; font-size: 14px; font-weight: 700; color: #232326; }
	.pp-label { display: block; font-size: 8px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; }
	.pp-tools { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
	.pp-tool { font-size: 10px; font-weight: 600; font-family: monospace; color: #475569; background: #f1f5f9; padding: 2px 6px; border-radius: 3px; }
	.pp-digest { font-size: 10px; font-weight: 600; color: #16a34a; }
</style>
