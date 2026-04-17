<script lang="ts">
	interface Props {
		tag: string;
		quote?: string | null;
	}
	let { tag, quote = null }: Props = $props();

	const colors: Record<string, { bg: string; text: string }> = {
		ownership_dodge: { bg: '#fef2f2', text: '#991b1b' },
		reasoning_loop: { bg: '#fffbeb', text: '#92400e' },
		permission_seeking: { bg: '#eff6ff', text: '#1e40af' },
		premature_stop: { bg: '#fdf4ff', text: '#7e22ce' },
		simplest_mentality: { bg: '#fff7ed', text: '#9a3412' },
		self_admitted_error: { bg: '#f0fdf4', text: '#166534' },
	};
	const style = $derived(colors[tag] || { bg: '#f1f5f9', text: '#334155' });
	const label = $derived(tag.replace(/_/g, ' '));
</script>

<span class="tag" style="background: {style.bg}; color: {style.text}" title={quote || ''}>
	{label}
</span>

<style>
	.tag {
		display: inline-block;
		font-size: 10px;
		font-weight: 600;
		padding: 2px 6px;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		cursor: default;
	}
</style>
