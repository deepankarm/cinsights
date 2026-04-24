<script lang="ts">
	import { onMount } from 'svelte';
	import { getTasks, getTaskStats, getUsers, getProjects } from '$lib/api';
	import type { TaskListItem, TaskStatsResponse } from '$lib/api';
	import { fmtTokens, fmtDate } from '$lib/format';

	let tasks: TaskListItem[] = $state([]);
	let stats: TaskStatsResponse | null = $state(null);
	let loading = $state(true);

	let search = $state('');
	let sortBy = $state('date');
	let filterUser = $state('');
	let filterProject = $state('');

	let users: string[] = $state([]);
	let projects: string[] = $state([]);

	async function loadTasks() {
		loading = true;
		try {
			const [t, s] = await Promise.all([
				getTasks(0, 100, filterUser || undefined, filterProject || undefined, search || undefined, sortBy),
				getTaskStats(filterUser || undefined, filterProject || undefined),
			]);
			tasks = t;
			stats = s;
		} catch (e) {
			console.error('Failed to load tasks', e);
		}
		loading = false;
	}

	onMount(async () => {
		const [u, p] = await Promise.all([getUsers(), getProjects()]);
		users = [...new Set(u.map((x: { user_id: string }) => x.user_id))].sort();
		projects = p.map((x: { name: string }) => x.name).sort();
		await loadTasks();
	});

	function handleFilter() { loadTasks(); }
</script>

<svelte:head><title>Tasks - cinsights</title></svelte:head>

<div class="page-header">
	<h1>Tasks</h1>
	{#if stats}
		<div class="stats-row">
			<span class="stat-badge">{stats.total_tasks} tasks</span>
			<span class="stat-badge">{stats.avg_turns_per_task} avg turns</span>
			<span class="stat-badge">{fmtTokens(stats.avg_tokens_per_task)} avg tokens</span>
		</div>
	{/if}
</div>

<div class="filter-bar">
	<input type="text" placeholder="Search tasks..." bind:value={search} onkeyup={(e) => { if ((e as KeyboardEvent).key === 'Enter') handleFilter(); }} class="search-input" />
	<select bind:value={filterProject} onchange={handleFilter}>
		<option value="">All projects</option>
		{#each projects as p}<option value={p}>{p}</option>{/each}
	</select>
	<select bind:value={filterUser} onchange={handleFilter}>
		<option value="">All developers</option>
		{#each users as u}<option value={u}>{u}</option>{/each}
	</select>
	<select bind:value={sortBy} onchange={handleFilter}>
		<option value="date">Newest first</option>
		<option value="cost">Most expensive</option>
		<option value="turns">Most turns</option>
	</select>
</div>

{#if loading}
	<div class="loading">Loading tasks...</div>
{:else if tasks.length === 0}
	<div class="empty">No tasks found. Run <code>cinsights analyze</code> to detect tasks in your sessions.</div>
{:else}
	<div class="task-table">
		<div class="table-header">
			<span class="col-name">Task</span>
			<span class="col-project">Project</span>
			<span class="col-user">Developer</span>
			<span class="col-turns">Turns</span>
			<span class="col-tokens">Tokens</span>
			<span class="col-waste">Waste</span>
			<span class="col-date">Date</span>
		</div>
		{#each tasks as task}
			<a href="/sessions/{encodeURIComponent(task.session_id)}" class="task-row">
				<span class="col-name">
					<span class="task-name">{task.name}</span>
					<span class="task-desc">{task.description}</span>
				</span>
				<span class="col-project">{task.project_name ?? '-'}</span>
				<span class="col-user">{task.user_id?.split('@')[0] ?? '-'}</span>
				<span class="col-turns">{task.turn_count}</span>
				<span class="col-tokens">{fmtTokens(task.prompt_tokens_total)}</span>
				<span class="col-waste">{task.estimated_waste_tokens ? fmtTokens(task.estimated_waste_tokens) : '-'}</span>
				<span class="col-date">{task.session_start_time ? fmtDate(task.session_start_time) : '-'}</span>
			</a>
		{/each}
	</div>
{/if}

<style>
	.page-header { display: flex; align-items: baseline; gap: 16px; margin-bottom: 20px; }
	h1 { font-size: 24px; font-weight: 800; color: #0f172a; }
	.stats-row { display: flex; gap: 8px; }
	.stat-badge { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 6px; background: #f1f5f9; color: #64748b; }

	.filter-bar { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
	.search-input { flex: 1; min-width: 200px; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; }
	.search-input:focus { outline: none; border-color: #3b82f6; }
	select { padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; background: white; cursor: pointer; }

	.loading, .empty { text-align: center; padding: 48px; color: #64748b; }
	.empty code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 12px; }

	.task-table { background: white; border: 1px solid #e8e5e0; border-radius: 12px; overflow: hidden; }
	.table-header { display: grid; grid-template-columns: 2fr 1fr 1fr 70px 80px 80px 100px; padding: 10px 16px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #94a3b8; border-bottom: 1px solid #e8e5e0; }
	.task-row { display: grid; grid-template-columns: 2fr 1fr 1fr 70px 80px 80px 100px; padding: 12px 16px; border-bottom: 1px solid #f1f5f9; text-decoration: none; color: inherit; transition: background 0.1s; align-items: center; }
	.task-row:hover { background: #fafafa; }
	.task-row:last-child { border-bottom: none; }

	.col-name { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
	.task-name { font-weight: 600; font-size: 13px; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.task-desc { font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.col-project, .col-user { font-size: 12px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.col-turns, .col-tokens, .col-waste, .col-date { font-size: 12px; color: #64748b; font-variant-numeric: tabular-nums; }

	@media (max-width: 768px) {
		.table-header { display: none; }
		.task-row { grid-template-columns: 1fr; gap: 4px; }
	}
</style>
