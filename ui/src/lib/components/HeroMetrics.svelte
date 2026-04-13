<script lang="ts">
	type Metric = { value: string; label: string; sub: string };
	let { metrics }: { metrics: Metric[] } = $props();
</script>

<div class="hero">
	{#each metrics as m}
		<div class="hero-metric">
			<div class="hero-value">{m.value}</div>
			<div class="hero-label">{m.label}</div>
			<div class="hero-sub">{m.sub}</div>
		</div>
	{/each}
</div>

<style>
	.hero { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }
	.hero-metric { background: white; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #e8e5e0; }
	.hero-value { font-size: 36px; font-weight: 800; letter-spacing: -2px; color: #232326; line-height: 1; }
	.hero-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #70707a; margin-top: 6px; }
	.hero-sub { font-size: 11px; color: #a1a1aa; margin-top: 2px; }
	@media (max-width: 768px) { .hero { grid-template-columns: repeat(2, 1fr); } }
</style>
