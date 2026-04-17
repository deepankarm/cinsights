<script lang="ts">
	import type { SessionRead } from '$lib/types';
	import { fmtTokens, gradeColor, gradeBg } from '$lib/format';

	let { sessions, compact = false, limit = 10 }: { sessions: SessionRead[]; compact?: boolean; limit?: number } = $props();

	let showAll = $state(false);
	const visible = $derived(showAll ? sessions : sessions.slice(0, limit));
	const hasMore = $derived(sessions.length > limit);

	function sessionGrade(s: SessionRead): string {
		const rate = s.error_count / Math.max(s.tool_call_count, 1);
		if (rate <= 0.05) return 'A';
		if (rate <= 0.10) return 'B';
		if (rate <= 0.20) return 'C';
		if (rate <= 0.35) return 'D';
		return 'F';
	}

	function displayId(id: string): string {
		if (id.startsWith('local:')) return id.split(':').slice(2).join(':').slice(0, 18);
		if (id.startsWith('entireio:')) return id.split(':')[1].slice(0, 8);
		return id.slice(0, 8);
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		const day = d.getDate().toString().padStart(2, '0');
		const mon = d.toLocaleString('en', { month: 'short' });
		const h = d.getHours().toString().padStart(2, '0');
		const m = d.getMinutes().toString().padStart(2, '0');
		return `${day} ${mon} ${h}:${m}`;
	}

	function formatDurationMs(ms: number): string {
		if (ms < 1000) return '<1s';
		const mins = Math.floor(ms / 60000);
		const secs = Math.floor((ms % 60000) / 1000);
		if (mins >= 60) return `${Math.floor(mins / 60)}h ${mins % 60}m`;
		if (mins > 0) return `${mins}m ${secs}s`;
		return `${secs}s`;
	}

	function activeDuration(s: SessionRead): string {
		if (s.active_duration_ms) return formatDurationMs(s.active_duration_ms);
		if (!s.end_time) return '-';
		const ms = new Date(s.end_time).getTime() - new Date(s.start_time).getTime();
		return formatDurationMs(ms);
	}

	function sourceColor(src: string): string {
		switch (src) {
			case 'local': return '#7c3aed';
			case 'entireio': return '#0891b2';
			case 'phoenix': return '#ea580c';
			default: return '#64748b';
		}
	}

	function agentColor(agent: string | null): string {
		switch (agent) {
			case 'claude-code': return '#c2410c';
			case 'codex': return '#15803d';
			case 'copilot': return '#1d4ed8';
			default: return '#64748b';
		}
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'analyzed': return '#16a34a';
			case 'indexed': return '#8b5cf6';
			case 'pending': return '#ca8a04';
			case 'failed': return '#dc2626';
			default: return '#64748b';
		}
	}

	function statusIcon(status: string): string {
		switch (status) {
			case 'analyzed': return '●';
			case 'indexed': return '○';
			case 'pending': return '◌';
			case 'failed': return '✗';
			default: return '·';
		}
	}
</script>

<div class="table-wrap">
	<table>
		<thead>
			<tr>
				<th class="col-grade"></th>
				<th class="col-session">Session</th>
				<th class="col-source">Source</th>
				{#if !compact}<th class="col-agent">Agent</th>{/if}
				<th class="col-time">Time</th>
				{#if !compact}<th class="col-model">Model</th>{/if}
				<th class="col-dur">Active</th>
				<th class="col-num">Tools</th>
				<th class="col-num">Errors</th>
				<th class="col-num">Tokens</th>
				{#if !compact}<th class="col-num">Insights</th>{/if}
				<th class="col-status">Status</th>
			</tr>
		</thead>
		<tbody>
			{#each visible as s}
				{@const grade = sessionGrade(s)}
				<tr style="background: {gradeBg(grade)}">
					<td class="cell-grade" style="color: {gradeColor(grade)}">{grade}</td>
					<td class="cell-session">
						<a href="/sessions/{s.id}" class="session-link" title={s.id}>{displayId(s.id)}</a>
					</td>
					<td>
						<span class="badge" style="background: {sourceColor(s.source ?? 'phoenix')}15; color: {sourceColor(s.source ?? 'phoenix')}; border-color: {sourceColor(s.source ?? 'phoenix')}30">
							{s.source ?? 'phoenix'}
						</span>
					</td>
					{#if !compact}
						<td>
							<span class="badge" style="background: {agentColor(s.agent_type)}10; color: {agentColor(s.agent_type)}; border-color: {agentColor(s.agent_type)}25" title={s.agent_version ? `v${s.agent_version}` : ''}>
								{s.agent_type ?? '-'}
							</span>
						</td>
					{/if}
					<td class="cell-dim">{formatDate(s.start_time)}</td>
					{#if !compact}<td class="cell-mono">{s.model ?? '-'}</td>{/if}
					<td class="cell-mono">{activeDuration(s)}</td>
					<td class="cell-num">{s.tool_call_count || '-'}</td>
					<td class="cell-num cell-err" class:has-errors={s.error_count > 0}>{s.error_count || '-'}</td>
					<td class="cell-num">{fmtTokens(s.total_tokens)}</td>
					{#if !compact}<td class="cell-num">{s.insight_count || '-'}</td>{/if}
					<td>
						<span class="status" style="color: {statusColor(s.status)}">
							{statusIcon(s.status)} {s.status}
						</span>
						{#if s.interrupt_count && s.interrupt_count > 0}
							<span class="interrupt-mini" title="{s.interrupt_count} user interrupt{s.interrupt_count > 1 ? 's' : ''}">{s.interrupt_count}x</span>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
	{#if hasMore}
		<button class="show-toggle" onclick={() => showAll = !showAll}>
			{showAll ? 'Show fewer' : `Show all ${sessions.length}`}
		</button>
	{/if}
</div>

<style>
	.table-wrap {
		background: white;
		border: 1px solid #e8e5e0;
		border-radius: 10px;
		overflow-x: auto;
	}
	table {
		width: 100%;
		min-width: 700px;
		border-collapse: collapse;
	}
	thead {
		position: sticky;
		top: 0;
	}
	th {
		text-align: left;
		padding: 10px 14px;
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		border-bottom: 2px solid #e8e5e0;
		background: #f8fafc;
		white-space: nowrap;
	}
	td {
		padding: 9px 14px;
		font-size: 13px;
		border-bottom: 1px solid rgba(0,0,0,0.04);
		color: #334155;
	}
	tr:last-child td { border-bottom: none; }
	tr:hover { filter: brightness(0.97); }

	.col-grade { width: 32px; }
	.col-session { min-width: 120px; }
	.col-source { min-width: 70px; }
	.col-agent { min-width: 100px; }
	.col-time { min-width: 110px; }
	.col-model { min-width: 120px; }
	.col-dur { min-width: 70px; }
	.col-num { min-width: 50px; text-align: right; }
	.col-status { min-width: 90px; }

	.cell-grade { font-size: 15px; font-weight: 800; text-align: center; }
	.cell-session { font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace; font-size: 12px; }
	.session-link { color: #2563eb; text-decoration: none; font-weight: 500; white-space: nowrap; }
	.session-link:hover { text-decoration: underline; color: #1d4ed8; }
	.cell-mono { font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace; font-size: 12px; color: #475569; }
	.cell-dim { font-size: 12px; color: #64748b; white-space: nowrap; }
	.cell-num { text-align: right; font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace; font-size: 12px; color: #475569; }
	.cell-err.has-errors { color: #ef4444; font-weight: 600; }
	.interrupt-mini { font-size: 9px; font-weight: 600; color: #92400e; background: #fffbeb; padding: 1px 4px; border-radius: 3px; margin-left: 4px; }

	.badge {
		display: inline-block;
		font-size: 11px;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 4px;
		border: 1px solid;
		white-space: nowrap;
	}
	.status { font-size: 12px; font-weight: 500; white-space: nowrap; }

	.show-toggle {
		display: block; margin: 12px auto; background: white; border: none;
		border-radius: 10px; padding: 10px 24px; font-size: 13px; font-weight: 500;
		color: #70707a; cursor: pointer; transition: all 0.15s;
	}
	.show-toggle:hover { color: #232326; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
</style>
