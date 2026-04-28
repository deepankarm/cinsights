<script lang="ts">
	import type { ThemeRead } from '$lib/types';
	import { avatarColor, fmtTokens } from '$lib/format';

	let { themes = [], topN = 25 }: { themes?: ThemeRead[]; topN?: number } = $props();

	let expanded = $state(false);

	const sorted = $derived([...themes].sort((a, b) => b.total_tokens - a.total_tokens));
	const visible = $derived(sorted.slice(0, topN));
	const hidden = $derived(sorted.slice(topN));

	// Date range across ALL themes (not just visible) so the timeline shows the
	// full project span.
	const allDates = $derived(
		themes
			.flatMap((t) => t.members.map((m) => m.date))
			.filter((d): d is string => d != null)
			.map((d) => new Date(d).getTime())
	);
	const dMin = $derived(allDates.length ? Math.min(...allDates) : 0);
	const dMax = $derived(allDates.length ? Math.max(...allDates) : 0);
	const spanMs = $derived(Math.max(dMax - dMin, 1));

	// User palette (only show legend when multi-dev)
	const allUsers = $derived(
		Array.from(new Set(themes.flatMap((t) => t.members.map((m) => m.user_id ?? '?'))))
	);
	const isMultiUser = $derived(allUsers.length > 1);

	// SVG layout
	const LEFT_PAD = 320;
	const RIGHT_PAD = 110;
	const TOP_PAD = 50;
	const BOTTOM_PAD = 30;
	const LANE_HEIGHT = 30;
	const WIDTH = 1300;
	const innerWidth = WIDTH - LEFT_PAD - RIGHT_PAD;
	const height = $derived(TOP_PAD + visible.length * LANE_HEIGHT + BOTTOM_PAD);

	function xOf(iso: string): number {
		const t = new Date(iso).getTime();
		return LEFT_PAD + ((t - dMin) / spanMs) * innerWidth;
	}

	const maxTok = $derived(
		Math.max(...themes.flatMap((t) => t.members.map((m) => m.tokens)), 1)
	);
	function rOf(tokens: number): number {
		return 3 + Math.sqrt(tokens / maxTok) * 9; // 3..12px
	}

	// Weekly tick marks
	function ticks(): { iso: string; label: string }[] {
		if (!allDates.length) return [];
		const out: { iso: string; label: string }[] = [];
		let cur = new Date(dMin);
		cur.setUTCHours(0, 0, 0, 0);
		const end = new Date(dMax);
		while (cur.getTime() <= end.getTime()) {
			out.push({
				iso: cur.toISOString(),
				label: `${cur.toLocaleString('en', { month: 'short' })} ${cur.getUTCDate()}`
			});
			cur = new Date(cur.getTime() + 7 * 24 * 3600 * 1000);
		}
		// Always include the rightmost edge
		const lastEdge = new Date(dMax);
		if (out.length === 0 || out[out.length - 1].iso !== lastEdge.toISOString()) {
			out.push({
				iso: lastEdge.toISOString(),
				label: `${lastEdge.toLocaleString('en', { month: 'short' })} ${lastEdge.getUTCDate()}`
			});
		}
		return out;
	}
	const tickList = $derived(ticks());

	function shortUser(uid: string | null): string {
		if (!uid) return '?';
		return uid.split('@')[0];
	}

	function truncate(s: string, n: number): string {
		return s.length <= n ? s : s.slice(0, n - 1) + '…';
	}

	function tooltipFor(themeName: string, taskName: string, user: string | null, date: string | null, tokens: number): string {
		const dateStr = date
			? new Date(date).toLocaleDateString('en', { month: 'short', day: 'numeric' })
			: '?';
		return `${themeName}\n${taskName}\n${shortUser(user)} · ${dateStr} · ${fmtTokens(tokens)}`;
	}
</script>

{#snippet swimlaneSvg()}
	<svg viewBox="0 0 {WIDTH} {height}" xmlns="http://www.w3.org/2000/svg">
		<!-- Weekly gridlines + axis labels -->
		{#each tickList as tick}
			{@const x = xOf(tick.iso)}
			<line x1={x} y1={TOP_PAD - 8} x2={x} y2={height - BOTTOM_PAD} stroke="#f1f5f9" stroke-width="1" />
			<text x={x} y={TOP_PAD - 16} font-size="10" fill="#94a3b8" text-anchor="middle">
				{tick.label}
			</text>
		{/each}

		<!-- Theme lanes -->
		{#each visible as theme, i}
			{@const y = TOP_PAD + i * LANE_HEIGHT + LANE_HEIGHT / 2}
			{@const x1 = theme.first_date ? xOf(theme.first_date) : LEFT_PAD}
			{@const x2 = theme.last_date ? xOf(theme.last_date) : LEFT_PAD}

			{#if i % 2 === 0}
				<rect x={LEFT_PAD} y={TOP_PAD + i * LANE_HEIGHT} width={innerWidth} height={LANE_HEIGHT} fill="#fafafa" />
			{/if}

			<text x={LEFT_PAD - 12} y={y + 4} font-size="12" fill="#0f172a" text-anchor="end" font-weight="500">
				<title>{theme.name}</title>
				{truncate(theme.name, 44)}
			</text>

			<line x1={x1} y1={y} x2={Math.max(x2, x1 + 2)} y2={y} stroke="#cbd5e1" stroke-width="2" stroke-linecap="round" />

			{#each theme.members as m}
				{#if m.date}
					<circle
						class="dot"
						cx={xOf(m.date)}
						cy={y}
						r={rOf(m.tokens)}
						fill={avatarColor(m.user_id ?? '?')}
						fill-opacity="0.78"
						stroke="white"
						stroke-width="1"
					>
						<title>{tooltipFor(theme.name, m.task_name, m.user_id, m.date, m.tokens)}</title>
					</circle>
				{/if}
			{/each}

			<text x={WIDTH - RIGHT_PAD + 12} y={y + 4} font-size="11" fill="#16a34a" font-weight="600">
				{fmtTokens(theme.total_tokens)}
			</text>
		{/each}
	</svg>
{/snippet}

{#if themes.length > 0}
	<div class="swimlane-wrap">
		<div class="swimlane-header">
			{#if isMultiUser}
				<div class="legend">
					{#each allUsers as user}
						<span class="legend-item">
							<span class="legend-dot" style="background: {avatarColor(user)}"></span>
							{shortUser(user)}
						</span>
					{/each}
				</div>
			{:else}
				<span></span>
			{/if}
			<button class="expand-btn" onclick={() => (expanded = true)} title="Expand chart">⛶</button>
		</div>

		<div class="chart-scroll">
			{@render swimlaneSvg()}
		</div>

		{#if hidden.length > 0}
			{@const tailTokens = hidden.reduce((s, t) => s + t.total_tokens, 0)}
			{@const tailTasks = hidden.reduce((s, t) => s + t.task_count, 0)}
			<div class="tail">
				+ {hidden.length} smaller themes · {tailTasks} tasks · {fmtTokens(tailTokens)} tokens
			</div>
		{/if}
	</div>

	{#if expanded}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="chart-overlay"
			onkeydown={(e) => {
				if (e.key === 'Escape') expanded = false;
			}}
		>
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="chart-overlay-backdrop" onclick={() => (expanded = false)}></div>
			<div class="chart-overlay-content">
				<div class="overlay-header">
					<h3>Themes <span class="dim">({themes.length} work areas)</span></h3>
					<button class="expand-btn" onclick={() => (expanded = false)} title="Close">✕</button>
				</div>
				{#if isMultiUser}
					<div class="legend">
						{#each allUsers as user}
							<span class="legend-item">
								<span class="legend-dot" style="background: {avatarColor(user)}"></span>
								{shortUser(user)}
							</span>
						{/each}
					</div>
				{/if}
				<div class="chart-scroll-overlay">
					{@render swimlaneSvg()}
				</div>
			</div>
		</div>
	{/if}
{/if}

<style>
	.swimlane-wrap {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.swimlane-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		font-size: 12px;
		color: #52525b;
	}
	.legend-item {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}
	.legend-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		display: inline-block;
	}
	.chart-scroll {
		overflow-x: auto;
	}
	svg {
		width: 100%;
		min-width: 800px;
		height: auto;
		display: block;
	}
	.expand-btn {
		background: none;
		border: 1px solid #e2e8f0;
		border-radius: 6px;
		padding: 2px 7px;
		cursor: pointer;
		font-size: 14px;
		color: #94a3b8;
		transition: color 0.15s, border-color 0.15s;
	}
	.expand-btn:hover {
		color: #3b82f6;
		border-color: #3b82f6;
	}
	.chart-overlay {
		position: fixed;
		inset: 0;
		z-index: 1000;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.chart-overlay-backdrop {
		position: absolute;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		backdrop-filter: blur(4px);
	}
	.chart-overlay-content {
		position: relative;
		z-index: 1;
		background: white;
		border-radius: 16px;
		padding: 24px 28px;
		width: 95vw;
		max-width: 1700px;
		max-height: 92vh;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		gap: 12px;
		box-shadow: 0 24px 48px rgba(0, 0, 0, 0.2);
	}
	.overlay-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 12px;
	}
	.overlay-header h3 {
		margin: 0;
		font-size: 16px;
		font-weight: 700;
		color: #232326;
	}
	.dim {
		font-size: 13px;
		font-weight: 400;
		color: #94a3b8;
	}
	.chart-scroll-overlay {
		overflow: auto;
		flex: 1;
	}
	.dot {
		transition: r 0.15s, fill-opacity 0.15s;
		cursor: default;
	}
	.dot:hover {
		fill-opacity: 1;
	}
	.tail {
		font-size: 12px;
		color: #94a3b8;
		padding-top: 8px;
		border-top: 1px solid #f1f5f9;
	}
</style>
