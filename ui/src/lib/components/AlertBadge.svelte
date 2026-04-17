<script lang="ts">
	interface Props {
		count: number;
		tooltip?: string;
	}
	let { count, tooltip = '' }: Props = $props();
</script>

{#if count > 0}
	<span class="badge" title={tooltip || `${count} alert${count > 1 ? 's' : ''}`}>
		{count}
	</span>
{/if}

<style>
	.badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 18px;
		height: 18px;
		font-size: 10px;
		font-weight: 700;
		background: #fef2f2;
		color: #dc2626;
		border: 1px solid #fecaca;
		border-radius: 9px;
		padding: 0 5px;
		cursor: default;
	}
</style>
