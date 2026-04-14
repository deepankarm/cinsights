<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getDoctorHealth, getDoctorRuns, getDoctorCost, getDoctorCoverage,
		type SystemHealthResponse, type RefreshRunRead,
		type CostSummaryResponse, type CoverageResponse,
	} from '$lib/api';
	import { fmtTokens, fmtBytes, fmtCost, fmtAgo, fmtDate, fmtSecs, fmtNum } from '$lib/format';

	let health: SystemHealthResponse | null = $state(null);
	let runs: RefreshRunRead[] = $state([]);
	let cost: CostSummaryResponse | null = $state(null);
	let coverage: CoverageResponse | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);

	let commandFilter = $state('');
	let statusFilter = $state('');
	let expandedErrors: Set<string> = $state(new Set());
	let showAllRuns = $state(false);
	const runsLimit = 15;

	const filteredRuns = $derived(runs.filter(r => {
		if (commandFilter && r.command !== commandFilter) return false;
		if (statusFilter && r.status !== statusFilter) return false;
		return true;
	}));

	const visibleRuns = $derived(showAllRuns ? filteredRuns : filteredRuns.slice(0, runsLimit));

	onMount(async () => {
		try {
			const [h, r, c, cov] = await Promise.all([
				getDoctorHealth(),
				getDoctorRuns(undefined, undefined, 0, 200),
				getDoctorCost(),
				getDoctorCoverage(),
			]);
			health = h;
			runs = r;
			cost = c;
			coverage = cov;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load doctor data';
		} finally {
			loading = false;
		}
	});

	function toggleError(id: string) {
		const next = new Set(expandedErrors);
		if (next.has(id)) next.delete(id); else next.add(id);
		expandedErrors = next;
	}

	function statusColor(s: string): string {
		return s === 'success' ? '#16a34a' : s === 'failed' ? '#dc2626' : '#f59e0b';
	}

	function cmdColor(c: string): string {
		return c === 'analyze' ? '#6366f1' : c === 'digest' ? '#0d9488' : '#3b82f6';
	}

	function sparklinePath(points: { timestamp: string; bytes: number }[]): string {
		if (points.length < 2) return '';
		const maxB = Math.max(...points.map(p => p.bytes));
		const minB = Math.min(...points.map(p => p.bytes));
		const range = maxB - minB || 1;
		const w = 120, h = 32;
		return points.map((p, i) => {
			const x = (i / (points.length - 1)) * w;
			const y = h - ((p.bytes - minB) / range) * (h - 4) - 2;
			return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
		}).join(' ');
	}

	function maxDailyTokens(trend: { prompt_tokens: number; completion_tokens: number }[]): number {
		return Math.max(...trend.map(d => d.prompt_tokens + d.completion_tokens), 1);
	}

	function maxScoreCount(dist: { count: number }[]): number {
		return Math.max(...dist.map(b => b.count), 1);
	}


	function runScope(run: RefreshRunRead): string {
		const m = run.metadata;
		if (!m) return '';
		if (m.project) return m.project as string;
		if (m.user) return m.user as string;
		return '';
	}

	function runScopeType(run: RefreshRunRead): string {
		const m = run.metadata;
		if (!m) return '';
		if (m.scope_type) return m.scope_type as string;
		if (m.project) return 'project';
		if (m.user) return 'user';
		return '';
	}

	function runDays(run: RefreshRunRead): string {
		const m = run.metadata;
		if (!m?.days) return '';
		return `${m.days}d`;
	}

	function runModel(run: RefreshRunRead): string {
		const model = run.metadata?.model as string | undefined;
		if (!model) return '';
		return model.replace('claude-', '').replace(/-2025\d+(-v\d+:\d+)?/, '');
	}
</script>

<svelte:head><title>Doctor — cinsights</title></svelte:head>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="loading" style="color: #dc2626">{error}</div>
{:else}

<!-- Section 1: System Health -->
{#if health}
<div class="section">
	<h2>System Health</h2>

	<div class="health-grid">
		<div class="health-card">
			<span class="hc-val">{health.total_sessions.toLocaleString()}</span>
			<span class="hc-label">Total Sessions</span>
		</div>
		<div class="health-card">
			<span class="hc-val" style="color: #6366f1">{health.indexed_sessions.toLocaleString()}</span>
			<span class="hc-label">Indexed</span>
		</div>
		<div class="health-card">
			<span class="hc-val" style="color: #16a34a">{health.analyzed_sessions.toLocaleString()}</span>
			<span class="hc-label">Analyzed</span>
		</div>
		<div class="health-card">
			<span class="hc-val" style="color: {health.failed_sessions > 0 ? '#dc2626' : '#a1a1aa'}">{health.failed_sessions}</span>
			<span class="hc-label">Failed</span>
		</div>
		<div class="health-card">
			<span class="hc-val">{health.total_projects}</span>
			<span class="hc-label">Projects</span>
		</div>
		<div class="health-card">
			<span class="hc-val">{health.total_developers}</span>
			<span class="hc-label">Developers</span>
		</div>
	</div>

	<div class="sub-row">
		<div class="db-card">
			<div class="db-info">
				<span class="db-val">{health.db_size_bytes ? fmtBytes(health.db_size_bytes) : '-'}</span>
				<span class="db-label">Database</span>
			</div>
			{#if health.db_size_history.length >= 2}
				<svg class="sparkline" viewBox="0 0 120 32" preserveAspectRatio="none">
					<path d={sparklinePath(health.db_size_history)} fill="none" stroke="#6366f1" stroke-width="1.5" />
				</svg>
			{/if}
		</div>

		{#each [
			{ label: 'Last Refresh', run: health.last_refresh },
			{ label: 'Last Analyze', run: health.last_analyze },
			{ label: 'Last Digest', run: health.last_digest },
		] as { label, run }}
			<div class="lr-card">
				<span class="lr-label">{label}</span>
				{#if run}
					<span class="lr-ago">{fmtAgo(run.completed_at ?? run.started_at)}</span>
					<span class="lr-detail">{fmtDate(run.started_at)} · {fmtSecs(run.wall_seconds)}</span>
				{:else}
					<span class="lr-ago" style="color: #a1a1aa">Never</span>
				{/if}
			</div>
		{/each}
	</div>

	<div class="config-block">
		<h3>Configuration</h3>
		<table class="config-table">
			<thead><tr><th>Setting</th><th>Value</th><th>Description</th></tr></thead>
			<tbody>
				<tr>
					<td class="ct-key">model</td>
					<td class="ct-val"><span class="config-tag">{health.config.provider}:{health.config.model}</span></td>
					<td class="ct-desc">LLM model used for session analysis and digest generation</td>
				</tr>
				{#each health.config.limits as lim}
					<tr>
						<td class="ct-key">{lim.key}</td>
						<td class="ct-val">{lim.value}</td>
						<td class="ct-desc">{lim.description}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
{/if}

<!-- Section 2: Operations Log -->
<div class="section">
	<h2>Operations Log <span class="dim">({filteredRuns.length})</span></h2>
	<div class="filter-bar">
		<select bind:value={commandFilter}>
			<option value="">All commands</option>
			<option value="refresh">Refresh</option>
			<option value="analyze">Analyze</option>
			<option value="digest">Digest</option>
		</select>
		<select bind:value={statusFilter}>
			<option value="">All statuses</option>
			<option value="success">Success</option>
			<option value="failed">Failed</option>
			<option value="running">Running</option>
		</select>
	</div>

	<table class="runs-table">
		<thead>
			<tr>
				<th></th>
				<th>Command</th>
				<th>Scope</th>
				<th>Time</th>
				<th>Duration</th>
				<th>Work</th>
				<th>Tokens</th>
				<th>Cost</th>
				<th>Model</th>
				<th></th>
			</tr>
		</thead>
		<tbody>
			{#each visibleRuns as run}
				<tr class:run-failed={run.status === 'failed'}>
					<td><span class="run-status" style="background: {statusColor(run.status)}"></span></td>
					<td><span class="run-cmd" style="color: {cmdColor(run.command)}">{run.command}</span></td>
					<td class="run-scope-cell">
						{#if runScopeType(run)}<span class="run-scope-type">{runScopeType(run)}</span>{/if}
						{#if runScope(run)}<span class="run-scope">{runScope(run)}</span>{/if}
						{#if runDays(run)}<span class="run-days">{runDays(run)}</span>{/if}
					</td>
					<td class="run-time">{fmtDate(run.started_at)}</td>
					<td class="run-dur">{fmtSecs(run.wall_seconds)}</td>
					<td class="run-work">
						{#if run.sessions_analyzed > 0}{run.sessions_analyzed} sessions{:else if run.digests_generated > 0}{run.digests_generated} digest{:else}-{/if}
					</td>
					<td class="run-tokens">{run.total_prompt_tokens + run.total_completion_tokens > 0 ? fmtTokens(run.total_prompt_tokens + run.total_completion_tokens) : '-'}</td>
					<td class="run-cost">{fmtCost(run.estimated_cost_usd)}</td>
					<td class="run-model">{runModel(run)}</td>
					<td>
						{#if run.error_message}
							<button class="run-err-toggle" onclick={() => toggleError(run.id)}>
								{expandedErrors.has(run.id) ? 'Hide' : 'Error'}
							</button>
						{/if}
					</td>
				</tr>
				{#if run.error_message && expandedErrors.has(run.id)}
					<tr><td colspan="10" class="run-error-cell"><div class="run-error">{run.error_message}</div></td></tr>
				{/if}
			{/each}
		</tbody>
	</table>
	{#if filteredRuns.length > runsLimit}
		<button class="show-more" onclick={() => showAllRuns = !showAllRuns}>
			{showAllRuns ? 'Show fewer' : `Show all ${filteredRuns.length} runs`}
		</button>
	{/if}
</div>

<!-- Section 3: Cost Dashboard -->
{#if cost}
<div class="section">
	<h2>Cost</h2>

	<div class="cost-summary">
		<div class="cs-card">
			<span class="cs-val">{fmtTokens(cost.total_prompt_tokens)}</span>
			<span class="cs-label">Input tokens</span>
		</div>
		<div class="cs-card">
			<span class="cs-val">{fmtTokens(cost.total_completion_tokens)}</span>
			<span class="cs-label">Output tokens</span>
		</div>
		<div class="cs-card accent">
			<span class="cs-val">{fmtCost(cost.estimated_cost_usd)}</span>
			<span class="cs-label">Estimated cost</span>
		</div>
	</div>

	<div class="cost-tables">
		<div class="cost-table-wrap">
			<h3>By Command</h3>
			<table class="cost-table">
				<thead><tr><th>Command</th><th>Runs</th><th>Input</th><th>Output</th><th>Est. Cost</th></tr></thead>
				<tbody>
					{#each cost.by_command as c}
						<tr>
							<td><span class="cmd-badge" style="color: {cmdColor(c.command)}">{c.command}</span></td>
							<td>{c.run_count}</td>
							<td>{fmtTokens(c.prompt_tokens)}</td>
							<td>{fmtTokens(c.completion_tokens)}</td>
							<td>{fmtCost(c.estimated_cost_usd)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div class="cost-table-wrap">
			<h3>By Project</h3>
			<table class="cost-table">
				<thead><tr><th>Project</th><th>Sessions</th><th>Input</th><th>Output</th><th>Est. Cost</th></tr></thead>
				<tbody>
					{#each cost.by_project as p}
						<tr>
							<td class="proj-name">{p.project_name}</td>
							<td>{p.session_count}</td>
							<td>{fmtTokens(p.prompt_tokens)}</td>
							<td>{fmtTokens(p.completion_tokens)}</td>
							<td>{fmtCost(p.estimated_cost_usd)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>

	{#if cost.daily_trend.length > 1}
		<div class="daily-chart">
			<h3>Daily Token Usage</h3>
			<div class="bar-chart">
				{#each cost.daily_trend as d}
					{@const total = d.prompt_tokens + d.completion_tokens}
					{@const pct = (total / maxDailyTokens(cost.daily_trend)) * 100}
					<div class="bar-col" title="{d.date}: {fmtTokens(total)}">
						<div class="bar" style="height: {Math.max(pct, 2)}%">
							<div class="bar-input" style="height: {total > 0 ? (d.prompt_tokens / total) * 100 : 0}%"></div>
							<div class="bar-output" style="height: {total > 0 ? (d.completion_tokens / total) * 100 : 0}%"></div>
						</div>
						<span class="bar-label">{d.date.slice(5)}</span>
					</div>
				{/each}
			</div>
			<div class="bar-legend">
				<span class="legend-item"><span class="legend-dot" style="background: #6366f1"></span> Input</span>
				<span class="legend-item"><span class="legend-dot" style="background: #a78bfa"></span> Output</span>
			</div>
		</div>
	{/if}
</div>
{/if}

<!-- Section 4: Coverage & Scoring -->
{#if coverage}
<div class="section">
	<h2>Coverage & Scoring</h2>

	<table class="cov-table">
		<thead>
			<tr><th>Project</th><th>Total</th><th>Indexed</th><th>Analyzed</th><th>Coverage</th><th>Avg Score</th></tr>
		</thead>
		<tbody>
			{#each coverage.projects as p}
				<tr>
					<td class="proj-name">{p.project_name}</td>
					<td>{p.total_sessions}</td>
					<td>{p.indexed}</td>
					<td>{p.analyzed}</td>
					<td>
						<div class="cov-bar-wrap">
							<div class="cov-bar" style="width: {Math.max(p.coverage_pct, 2)}%; background: {p.coverage_pct >= 50 ? '#16a34a' : p.coverage_pct >= 20 ? '#eab308' : '#dc2626'}"></div>
							<span class="cov-pct">{p.coverage_pct}%</span>
						</div>
					</td>
					<td>{fmtNum(p.avg_interestingness)}</td>
				</tr>
			{/each}
		</tbody>
	</table>

	{#if coverage.score_distribution.some(b => b.count > 0)}
		<div class="score-dist">
			<h3>Score Distribution</h3>
			{#each coverage.score_distribution as b}
				<div class="score-row">
					<span class="score-bucket">{b.bucket}</span>
					<div class="score-bar-wrap">
						<div class="score-bar" style="width: {(b.count / maxScoreCount(coverage.score_distribution)) * 100}%"></div>
					</div>
					<span class="score-count">{b.count}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>
{/if}

{/if}

<style>
	.loading { text-align: center; padding: 80px; color: #94a3b8; }
	.section { margin-bottom: 32px; }
	h2 { font-size: 17px; font-weight: 700; color: #232326; margin-bottom: 14px; }
	h3 { font-size: 13px; font-weight: 600; color: #52525b; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
	.dim { font-size: 13px; font-weight: 400; color: #a1a1aa; }

	/* Health */
	.health-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-bottom: 10px; }
	.health-card { background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 14px 16px; }
	.hc-val { display: block; font-size: 22px; font-weight: 800; color: #232326; letter-spacing: -0.5px; font-variant-numeric: tabular-nums; }
	.hc-label { font-size: 11px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }

	.sub-row { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px; margin-bottom: 10px; }
	.db-card { background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 12px 14px; display: flex; align-items: center; justify-content: space-between; }
	.db-val { display: block; font-size: 15px; font-weight: 700; color: #232326; }
	.db-label { font-size: 11px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }
	.sparkline { width: 80px; height: 28px; flex-shrink: 0; }

	.lr-card { background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 12px 14px; }
	.lr-label { display: block; font-size: 10px; font-weight: 600; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 2px; }
	.lr-ago { display: block; font-size: 14px; font-weight: 700; color: #232326; }
	.lr-detail { font-size: 11px; color: #a1a1aa; }

	.config-block { background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 14px 16px; }
	.config-table { border-collapse: collapse; font-size: 12px; width: 100%; }
	.config-table th { text-align: left; font-size: 10px; font-weight: 600; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; padding: 4px 10px; border-bottom: 1px solid #f1f5f9; }
	.ct-key { padding: 5px 10px; color: #52525b; font-family: monospace; font-size: 11px; white-space: nowrap; }
	.ct-val { padding: 5px 10px; color: #232326; font-family: monospace; font-size: 12px; font-weight: 600; }
	.ct-desc { padding: 5px 10px; color: #a1a1aa; font-size: 11px; }
	.config-tag { background: #eef2ff; color: #6366f1; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 11px; }

	/* Ops Log */
	.filter-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
	.filter-bar select { padding: 6px 10px; border: 1px solid #e8e5e0; border-radius: 8px; font-size: 12px; background: white; color: #232326; cursor: pointer; }
	.runs-table { width: 100%; border-collapse: separate; border-spacing: 0 2px; font-size: 12px; }
	.runs-table th { text-align: left; font-size: 10px; font-weight: 600; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; padding: 4px 8px; white-space: nowrap; }
	.runs-table td { padding: 6px 8px; background: white; color: #52525b; white-space: nowrap; }
	.runs-table tr:first-child td:first-child { border-radius: 8px 0 0 8px; }
	.runs-table tr:first-child td:last-child { border-radius: 0 8px 8px 0; }
	.runs-table tbody tr:hover td { background: #f8fafc; }
	.runs-table tr.run-failed td { background: #fef2f2; }
	.run-status { display: inline-block; width: 7px; height: 7px; border-radius: 50%; }
	.run-cmd { font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em; }
	.run-scope-cell { display: flex; align-items: center; gap: 6px; }
	.run-scope-type { font-size: 10px; color: #a1a1aa; }
	.run-scope { font-size: 12px; font-weight: 600; color: #232326; overflow: hidden; text-overflow: ellipsis; max-width: 180px; }
	.run-days { font-size: 10px; color: #94a3b8; font-family: monospace; }
	.run-time { font-size: 11px; color: #a1a1aa; }
	.run-dur { font-size: 11px; font-family: monospace; color: #475569; }
	.run-work { font-size: 11px; color: #475569; }
	.run-tokens { font-size: 11px; font-family: monospace; color: #475569; }
	.run-cost { font-size: 11px; font-family: monospace; color: #7c3aed; }
	.run-model { font-size: 10px; color: #a1a1aa; font-family: monospace; }
	.run-err-toggle { background: none; border: 1px solid #fca5a5; border-radius: 4px; padding: 2px 8px; font-size: 10px; color: #dc2626; cursor: pointer; }
	.run-error-cell { padding: 0 !important; background: none !important; }
	.run-error { padding: 8px 12px 8px 28px; font-size: 11px; color: #991b1b; background: #fef2f2; border-radius: 0 0 8px 8px; font-family: monospace; white-space: pre-wrap; word-break: break-all; }
	.show-more { display: block; margin: 12px auto 0; background: white; border: 1px solid #e8e5e0; border-radius: 10px; padding: 10px 24px; font-size: 13px; font-weight: 500; color: #70707a; cursor: pointer; transition: all 0.15s; }
	.show-more:hover { color: #232326; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }

	/* Cost */
	.cost-summary { display: flex; gap: 8px; margin-bottom: 16px; }
	.cs-card { flex: 1; background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 16px; }
	.cs-card.accent { background: linear-gradient(135deg, #eef2ff, #f5f3ff); border-color: #c7d2fe; }
	.cs-val { display: block; font-size: 22px; font-weight: 800; color: #232326; letter-spacing: -0.5px; }
	.cs-label { font-size: 11px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; }

	.cost-tables { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
	.cost-table-wrap { background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 16px; overflow: auto; }
	.cost-table { width: 100%; border-collapse: collapse; font-size: 12px; }
	.cost-table th { text-align: left; font-size: 10px; font-weight: 600; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; padding: 4px 8px; border-bottom: 1px solid #f1f5f9; }
	.cost-table td { padding: 6px 8px; color: #475569; }
	.cost-table tr:hover td { background: #f8fafc; }
	.cmd-badge { font-weight: 700; font-size: 11px; }
	.proj-name { font-family: monospace; font-weight: 600; color: #232326; }

	.daily-chart { background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 16px; }
	.bar-chart { display: flex; align-items: flex-end; gap: 3px; height: 100px; padding-bottom: 20px; position: relative; }
	.bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; position: relative; }
	.bar { width: 100%; max-width: 24px; border-radius: 3px 3px 0 0; display: flex; flex-direction: column; justify-content: flex-end; position: absolute; bottom: 0; overflow: hidden; }
	.bar-input { background: #6366f1; }
	.bar-output { background: #a78bfa; }
	.bar-label { position: absolute; bottom: -18px; font-size: 9px; color: #a1a1aa; white-space: nowrap; }
	.bar-legend { display: flex; gap: 12px; margin-top: 8px; justify-content: center; }
	.legend-item { font-size: 10px; color: #a1a1aa; display: flex; align-items: center; gap: 4px; }
	.legend-dot { width: 8px; height: 8px; border-radius: 2px; }

	/* Coverage */
	.cov-table { width: 100%; border-collapse: collapse; font-size: 12px; background: white; border: 1px solid #e8e5e0; border-radius: 12px; overflow: hidden; }
	.cov-table th { text-align: left; font-size: 10px; font-weight: 600; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.04em; padding: 10px 12px; border-bottom: 1px solid #f1f5f9; }
	.cov-table td { padding: 8px 12px; color: #475569; border-bottom: 1px solid #f8fafc; }
	.cov-table tr:last-child td { border-bottom: none; }
	.cov-table tr:hover td { background: #f8fafc; }
	.cov-bar-wrap { display: flex; align-items: center; gap: 8px; min-width: 120px; }
	.cov-bar { height: 6px; border-radius: 3px; transition: width 0.3s; }
	.cov-pct { font-size: 11px; font-weight: 600; color: #475569; white-space: nowrap; }

	.score-dist { margin-top: 16px; background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 16px; }
	.score-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
	.score-bucket { font-size: 11px; font-family: monospace; color: #52525b; width: 56px; flex-shrink: 0; }
	.score-bar-wrap { flex: 1; height: 14px; background: #f4f4f5; border-radius: 3px; overflow: hidden; }
	.score-bar { height: 100%; background: linear-gradient(90deg, #6366f1, #8b5cf6); border-radius: 3px; transition: width 0.3s; }
	.score-count { font-size: 11px; font-weight: 600; color: #475569; width: 36px; text-align: right; }

	@media (max-width: 768px) {
		.health-grid { grid-template-columns: repeat(3, 1fr); }
		.sub-row { grid-template-columns: 1fr 1fr; }
		.cost-tables { grid-template-columns: 1fr; }
		.cost-summary { flex-direction: column; }
	}
</style>
