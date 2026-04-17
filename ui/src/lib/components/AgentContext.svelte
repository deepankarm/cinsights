<script lang="ts">
	import type { AlertRead } from '$lib/types';
	import AlertBadge from './AlertBadge.svelte';

	interface Props {
		agentVersion?: string | null;
		effortLevel?: string | null;
		adaptiveThinkingDisabled?: boolean | null;
		interruptCount?: number | null;
		alerts?: AlertRead[];
	}
	let {
		agentVersion = null,
		effortLevel = null,
		adaptiveThinkingDisabled = null,
		interruptCount = null,
		alerts = [],
	}: Props = $props();

	let expanded = $state(false);

	const hasContent = $derived(
		agentVersion || effortLevel || (interruptCount && interruptCount > 0) || alerts.length > 0
	);

	const alertKindLabels: Record<string, string> = {
		destructive_rm: 'rm -rf',
		force_push: 'Force push',
		hard_reset: 'Hard reset',
		credential_exposure: 'Credential access',
		pipe_to_shell: 'Pipe to shell',
		chmod_world_writable: 'chmod 777',
		sql_drop: 'SQL DROP',
	};
</script>

{#if hasContent}
<div class="agent-context" class:expanded>
	<button class="toggle" onclick={() => expanded = !expanded}>
		<span class="toggle-label">
			Agent Context
			{#if alerts.length > 0}
				<AlertBadge count={alerts.length} />
			{/if}
			{#if interruptCount && interruptCount > 0}
				<span class="interrupt-pill">{interruptCount} interrupt{interruptCount > 1 ? 's' : ''}</span>
			{/if}
		</span>
		<span class="toggle-arrow">{expanded ? '−' : '+'}</span>
	</button>

	{#if expanded}
	<div class="content">
		<div class="grid">
			<div class="col">
				<h4>Harness</h4>
				<dl>
					{#if agentVersion}
						<dt>Version</dt><dd>{agentVersion}</dd>
					{/if}
					{#if effortLevel}
						<dt>Effort</dt><dd class="effort {effortLevel}">{effortLevel}</dd>
					{/if}
					{#if adaptiveThinkingDisabled !== null}
						<dt>Adaptive thinking</dt><dd>{adaptiveThinkingDisabled ? 'disabled' : 'enabled'}</dd>
					{/if}
				</dl>
			</div>

			<div class="col">
				<h4>Friction Signals</h4>
				{#if interruptCount && interruptCount > 0}
					<p class="signal">{interruptCount} user interrupt{interruptCount > 1 ? 's' : ''}</p>
				{/if}
				{#if alerts.length > 0}
					<div class="alert-list">
						{#each alerts as alert}
							<div class="alert-row">
								<span class="alert-kind">{alertKindLabels[alert.alert_kind] || alert.alert_kind}</span>
								<span class="alert-evidence" title={alert.evidence}>{alert.evidence.slice(0, 80)}</span>
							</div>
						{/each}
					</div>
				{:else}
					<p class="signal muted">No dangerous operations detected</p>
				{/if}
			</div>
		</div>
	</div>
	{/if}
</div>
{/if}

<style>
	.agent-context {
		border: 1px solid #e8e5e0;
		border-radius: 12px;
		background: #fafaf9;
		margin-bottom: 20px;
		overflow: hidden;
	}
	.toggle {
		width: 100%;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 10px 16px;
		background: transparent;
		border: none;
		cursor: pointer;
		font-size: 13px;
		font-weight: 600;
		color: #475569;
	}
	.toggle:hover { background: #f1f5f9; }
	.toggle-label { display: flex; align-items: center; gap: 8px; }
	.toggle-arrow { font-size: 16px; color: #94a3b8; }
	.interrupt-pill {
		font-size: 10px;
		font-weight: 600;
		padding: 2px 6px;
		background: #fffbeb;
		color: #92400e;
		border-radius: 4px;
	}
	.content { padding: 0 16px 16px; }
	.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
	h4 { font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; margin: 0 0 8px; }
	dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 12px; margin: 0; }
	dt { color: #94a3b8; }
	dd { color: #334155; margin: 0; }
	.effort { font-weight: 600; }
	.effort.high, .effort.max { color: #16a34a; }
	.effort.medium { color: #d97706; }
	.effort.low { color: #94a3b8; }
	.signal { font-size: 12px; color: #475569; margin: 0 0 6px; }
	.signal.muted { color: #94a3b8; }
	.alert-list { display: flex; flex-direction: column; gap: 4px; }
	.alert-row { display: flex; gap: 8px; font-size: 11px; align-items: baseline; }
	.alert-kind { font-weight: 600; color: #dc2626; white-space: nowrap; }
	.alert-evidence { color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	@media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
