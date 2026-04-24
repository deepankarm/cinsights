<script lang="ts">
	import { onMount } from 'svelte';
	import { Chart } from './chartConfig';
	import type { ChartConfiguration, Chart as ChartType } from 'chart.js';

	let {
		labels,
		data,
		color = '#6366f1',
		horizontal = false,
		height = 200,
		valueFormat = (v: number) => String(v),
		barGradient = true,
	}: {
		labels: string[];
		data: number[];
		color?: string;
		horizontal?: boolean;
		height?: number;
		valueFormat?: (v: number) => string;
		barGradient?: boolean;
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: ChartType | null = null;

	function hexToRgb(hex: string): { r: number; g: number; b: number } {
		const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
		return result ? {
			r: parseInt(result[1], 16),
			g: parseInt(result[2], 16),
			b: parseInt(result[3], 16),
		} : { r: 99, g: 102, b: 241 };
	}

	function createBarGradient(): CanvasGradient | string {
		if (!canvas || !barGradient) return color;
		const ctx = canvas.getContext('2d');
		if (!ctx) return color;
		const { r, g, b } = hexToRgb(color);
		const gradient = horizontal
			? ctx.createLinearGradient(0, 0, canvas.width, 0)
			: ctx.createLinearGradient(0, canvas.height, 0, 0);
		gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.5)`);
		gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.9)`);
		return gradient;
	}

	function buildConfig(): ChartConfiguration<'bar'> {
		const indexAxis = horizontal ? 'y' as const : 'x' as const;
		const valueAxis = horizontal ? 'x' : 'y';
		const categoryAxis = horizontal ? 'y' : 'x';

		return {
			type: 'bar',
			data: {
				labels,
				datasets: [{
					data,
					backgroundColor: createBarGradient(),
					borderRadius: horizontal ? { topRight: 5, bottomRight: 5 } : { topLeft: 4, topRight: 4 },
					borderSkipped: false,
					maxBarThickness: horizontal ? 12 : undefined,
				}],
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				indexAxis,
				scales: {
					[valueAxis]: {
						grid: { color: '#f1f5f9' },
						ticks: {
							font: { size: 10 },
							callback: (v) => valueFormat(v as number),
						},
					},
					[categoryAxis]: {
						grid: { display: false },
						ticks: {
							font: { size: horizontal ? 12 : 10 },
							color: '#52525b',
						},
					},
				},
				plugins: {
					tooltip: {
						callbacks: {
							label: (ctx) => valueFormat(ctx.parsed[horizontal ? 'x' : 'y'] as number),
						},
					},
				},
			},
		};
	}

	onMount(() => {
		chart = new Chart(canvas, buildConfig());
		return () => {
			chart?.destroy();
			chart = null;
		};
	});

	$effect(() => {
		void labels;
		void data;
		void color;
		void horizontal;

		if (chart) {
			chart.destroy();
			chart = new Chart(canvas, buildConfig());
		}
	});
</script>

<div class="bar-chart-wrap" style="height: {height}px">
	<canvas bind:this={canvas}></canvas>
</div>

<style>
	.bar-chart-wrap {
		position: relative;
		width: 100%;
	}
</style>
