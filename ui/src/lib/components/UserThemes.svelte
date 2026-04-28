<script lang="ts">
	import type { UserThemeRead } from '$lib/types';
	import { fmtTokens } from '$lib/format';

	let {
		themes = [],
		defaultLimit = 6,
	}: { themes?: UserThemeRead[]; defaultLimit?: number } = $props();

	let showAll = $state(false);
	let openThemes: Set<string> = $state(new Set());

	const visible = $derived(showAll ? themes : themes.slice(0, defaultLimit));

	function toggle(id: string) {
		const next = new Set(openThemes);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		openThemes = next;
	}

	function relativeDate(iso: string | null): string {
		if (!iso) return '-';
		const ts = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
		const days = Math.floor((Date.now() - new Date(ts).getTime()) / 86_400_000);
		if (days <= 0) return 'today';
		if (days === 1) return '1d ago';
		if (days < 14) return `${days}d ago`;
		if (days < 60) return `${Math.round(days / 7)}w ago`;
		return `${Math.round(days / 30)}mo ago`;
	}

	function shareLabel(t: UserThemeRead): string {
		if (t.theme_dev_count <= 1) return 'solo';
		if (t.share_pct >= 60) return `${Math.round(t.share_pct)}% — primary owner`;
		if (t.share_pct >= 25) return `${Math.round(t.share_pct)}% of theme`;
		return `${Math.round(t.share_pct)}%`;
	}

	function shortDate(iso: string | null): string {
		if (!iso) return '';
		const ts = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
		return new Date(ts).toLocaleDateString();
	}
</script>

{#if themes.length > 0}
	<div class="ut-list">
		{#each visible as t (t.theme_id)}
			{@const isOpen = openThemes.has(t.theme_id)}
			<div class="theme-block" class:open={isOpen}>
				<button class="theme-row" onclick={() => toggle(t.theme_id)} aria-expanded={isOpen}>
					<span class="th-arrow" class:rotated={isOpen}>▸</span>
					<span class="th-name" title={t.theme_name}>{t.theme_name}</span>
					<a class="th-project" href="/projects/{encodeURIComponent(t.project_name)}" onclick={(e) => e.stopPropagation()} title="Open project">{t.project_name}</a>
					<span class="th-tokens">{fmtTokens(t.user_tokens)}</span>
					<span class="th-share">
						{#if t.theme_dev_count > 1}
							<span class="bar"><span class="bar-fill" style="width: {Math.min(100, t.share_pct)}%"></span></span>
						{/if}
						<span class="bar-label" class:dim={t.theme_dev_count <= 1}>{shareLabel(t)}</span>
					</span>
					<span class="th-tasks">{t.user_task_count} task{t.user_task_count === 1 ? '' : 's'}</span>
					<span class="th-date">{relativeDate(t.last_active)}</span>
				</button>

				{#if isOpen && t.tasks.length > 0}
					<div class="task-rows">
						{#each t.tasks as task (task.task_id)}
							<a class="task-row" href="/sessions/{encodeURIComponent(task.session_id)}" title="Open session">
								<span class="tr-name">{task.name}</span>
								<span class="tr-date">{shortDate(task.date)}</span>
								<span class="tr-turns">{task.turn_count} turn{task.turn_count === 1 ? '' : 's'}</span>
								<span class="tr-tokens">{fmtTokens(task.tokens)}</span>
								<span class="tr-go" aria-hidden="true">→</span>
							</a>
						{/each}
					</div>
				{/if}
			</div>
		{/each}
	</div>

	{#if themes.length > defaultLimit}
		<button class="show-more" onclick={() => (showAll = !showAll)}>
			{showAll ? 'Show fewer' : `Show all ${themes.length} themes`}
		</button>
	{/if}
{/if}

<style>
	.ut-list {
		background: white;
		border: 1px solid #e8e5e0;
		border-radius: 10px;
		overflow: hidden;
	}
	.theme-block {
		border-bottom: 1px solid #f1f5f9;
	}
	.theme-block:last-child {
		border-bottom: none;
	}
	.theme-block.open {
		background: #fafafa;
	}

	.theme-row {
		display: grid;
		grid-template-columns: 16px minmax(180px, 2fr) 1fr 70px minmax(140px, 1.4fr) 70px 80px;
		gap: 12px;
		align-items: center;
		width: 100%;
		padding: 10px 14px;
		background: none;
		border: none;
		text-align: left;
		font-size: 13px;
		cursor: pointer;
		transition: background 0.1s;
	}
	.theme-row:hover {
		background: #f1f5f9;
	}
	.theme-row:hover .th-name {
		color: #3b82f6;
	}
	.th-arrow {
		font-size: 11px;
		color: #94a3b8;
		text-align: center;
		transition: transform 0.15s;
	}
	.th-arrow.rotated {
		transform: rotate(90deg);
	}
	.th-name {
		font-weight: 600;
		color: #0f172a;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		transition: color 0.1s;
	}
	.th-project {
		color: #64748b;
		text-decoration: none;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.th-project:hover {
		color: #3b82f6;
		text-decoration: underline;
	}
	.th-tokens {
		color: #16a34a;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		text-align: right;
	}
	.th-share {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: #64748b;
	}
	.bar {
		flex: 0 0 60px;
		height: 6px;
		background: #f1f5f9;
		border-radius: 3px;
		overflow: hidden;
	}
	.bar-fill {
		display: block;
		height: 100%;
		background: #3b82f6;
		border-radius: 3px;
	}
	.bar-label {
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}
	.bar-label.dim {
		color: #cbd5e1;
		font-style: italic;
	}
	.th-tasks {
		color: #94a3b8;
		font-size: 12px;
		font-variant-numeric: tabular-nums;
		text-align: right;
	}
	.th-date {
		color: #94a3b8;
		font-size: 12px;
		font-variant-numeric: tabular-nums;
		text-align: right;
	}

	/* Nested task rows under an expanded theme */
	.task-rows {
		padding: 4px 14px 10px 42px;
		background: white;
		border-top: 1px solid #f1f5f9;
	}
	.task-row {
		display: grid;
		grid-template-columns: 1fr 90px 70px 70px 16px;
		gap: 12px;
		align-items: center;
		padding: 6px 10px;
		font-size: 12px;
		text-decoration: none;
		color: inherit;
		border-radius: 6px;
		transition: background 0.1s;
	}
	.task-row:hover {
		background: #f8fafc;
	}
	.task-row:hover .tr-name {
		color: #3b82f6;
	}
	.task-row:hover .tr-go {
		color: #3b82f6;
		transform: translateX(2px);
	}
	.tr-name {
		color: #334155;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		transition: color 0.1s;
	}
	.tr-date,
	.tr-turns {
		color: #94a3b8;
		font-size: 11px;
		font-variant-numeric: tabular-nums;
		text-align: right;
		white-space: nowrap;
	}
	.tr-tokens {
		color: #16a34a;
		font-variant-numeric: tabular-nums;
		text-align: right;
	}
	.tr-go {
		color: #cbd5e1;
		text-align: center;
		transition: color 0.1s, transform 0.1s;
	}

	.show-more {
		display: block;
		margin: 8px auto 0;
		font-size: 12px;
		color: #3b82f6;
		background: none;
		border: none;
		cursor: pointer;
	}
	.show-more:hover {
		text-decoration: underline;
	}
</style>
