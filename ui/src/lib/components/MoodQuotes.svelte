<script lang="ts">
	import type { MoodGroup } from '$lib/api';

	let { moodGroups }: { moodGroups: MoodGroup[] } = $props();
	let hoveredMood: string | null = $state(null);

	const MOOD_META: Record<string, { icon: string; color: string; bg: string; label: string }> = {
		frustrated: { icon: '😤', color: '#dc2626', bg: '#fef2f2', label: 'Frustrated' },
		curious:    { icon: '🤔', color: '#2563eb', bg: '#eff6ff', label: 'Curious' },
		amused:     { icon: '😄', color: '#ca8a04', bg: '#fefce8', label: 'Amused' },
		relieved:   { icon: '😮‍💨', color: '#16a34a', bg: '#f0fdf4', label: 'Relieved' },
		assertive:  { icon: '✋', color: '#7c3aed', bg: '#f5f3ff', label: 'Assertive' },
	};
</script>

{#if moodGroups.length > 0}
	<div class="mood-section"
		onmouseenter={() => hoveredMood = 'all'}
		onmouseleave={() => hoveredMood = null}>
		<h3>Things you've said when you were</h3>
		{#each moodGroups as group}
			{@const meta = MOOD_META[group.mood] ?? { icon: '💬', color: '#64748b', bg: '#f8fafc', label: group.mood }}
			{@const isHovered = hoveredMood === 'all'}
			{@const visible = isHovered ? group.quotes : group.quotes.slice(0, 3)}
			<div class="mood-row">
				<div class="mood-tag">
					<span class="mood-icon">{meta.icon}</span>
					<strong>{meta.label}</strong>
					<span class="mood-cnt">{group.quotes.length}</span>
				</div>
				<div class="mood-quotes-list">
					{#each visible as q}
						<div class="mq">{#if isHovered}&ldquo;{q.quote}&rdquo;{:else}&ldquo;{q.quote.length > 100 ? q.quote.slice(0, 100) + '...' : q.quote}&rdquo;{/if}</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>
{/if}

<style>
	.mood-section { background: white; border: 1px solid #e8e5e0; border-radius: 12px; padding: 16px; margin-top: 12px; }
	h3 { font-size: 13px; font-weight: 700; color: #232326; margin-bottom: 10px; }
	.mood-row { display: flex; gap: 12px; padding: 8px 4px; border-bottom: 1px solid #f4f4f5; align-items: baseline; border-radius: 6px; cursor: default; transition: background 0.1s; }
	.mood-row:last-child { border-bottom: none; }
	.mood-row:hover { background: #fafaf9; }
	.mood-tag { display: flex; align-items: center; gap: 5px; flex-shrink: 0; min-width: 120px; font-size: 13px; color: #232326; }
	.mood-icon { font-size: 16px; }
	.mood-cnt { font-size: 10px; font-weight: 600; color: #a1a1aa; }
	.mood-quotes-list { display: flex; flex-direction: column; gap: 4px; }
	.mq { font-size: 13px; color: #475569; font-style: italic; line-height: 1.4; }
</style>
