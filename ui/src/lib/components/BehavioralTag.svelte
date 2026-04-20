<script lang="ts">
	let { label }: { label: string } = $props();
</script>

<span class="label-tag">{label}</span>

<style>
	.label-tag {
		display: inline-block;
		font-size: 10px;
		font-weight: 600;
		padding: 2px 6px;
		border-radius: 4px;
		background: #f1f5f9;
		color: #475569;
		text-transform: lowercase;
		letter-spacing: 0.02em;
	}
</style>
