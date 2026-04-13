<script lang="ts">
	type Metric = { value: string; label: string; sub: string; color?: string };
	let { metrics }: { metrics: Metric[] } = $props();

	const defaultColors = ['#6366f1', '#8b5cf6', '#3b82f6', '#0d9488'];
</script>

<div class="hero">
	{#each metrics as m, i}
		<div class="hero-metric">
			<div class="hero-value" style="color: {m.color ?? defaultColors[i % defaultColors.length]}">{m.value}</div>
			<div class="hero-label">{m.label}</div>
			<div class="hero-sub">{m.sub}</div>
		</div>
	{/each}
</div>

<style>
	.hero { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }
	.hero-metric {
		background: white; border-radius: 16px; padding: 22px 24px; text-align: center;
		border: 1px solid #e8e5e0; transition: transform 0.2s, box-shadow 0.2s;
	}
	.hero-metric:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
	.hero-value { font-size: 36px; font-weight: 800; letter-spacing: -2px; line-height: 1; font-variant-numeric: tabular-nums; }
	.hero-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #70707a; margin-top: 6px; }
	.hero-sub { font-size: 11px; color: #a1a1aa; margin-top: 2px; }
	@media (max-width: 768px) { .hero { grid-template-columns: repeat(2, 1fr); } }
</style>
