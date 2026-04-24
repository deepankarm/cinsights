<script lang="ts">
	import { onMount } from 'svelte';
	import { Chart, COLORS } from './chartConfig';
	import type { Chart as ChartType } from 'chart.js';
	import { fmtTokens } from '$lib/format';

	let {
		whiskerLow,
		q1,
		median,
		q3,
		whiskerHigh,
		label = 'Token Distribution',
		height = 90,
	}: {
		whiskerLow: number;
		q1: number;
		median: number;
		q3: number;
		whiskerHigh: number;
		label?: string;
		height?: number;
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: ChartType | null = null;

	// Custom box plot drawn via a plugin since Chart.js doesn't have native box plots
	const boxPlotPlugin = {
		id: 'boxPlotCustom',
		afterDraw(chartInstance: ChartType) {
			const ctx = chartInstance.ctx;
			const xScale = chartInstance.scales['x'];
			if (!xScale) return;

			const cy = chartInstance.chartArea.top + (chartInstance.chartArea.bottom - chartInstance.chartArea.top) / 2;
			const boxH = 28;

			const xLow = xScale.getPixelForValue(whiskerLow);
			const xQ1 = xScale.getPixelForValue(q1);
			const xMed = xScale.getPixelForValue(median);
			const xQ3 = xScale.getPixelForValue(q3);
			const xHigh = xScale.getPixelForValue(whiskerHigh);

			// Whisker lines
			ctx.save();
			ctx.strokeStyle = '#94a3b8';
			ctx.lineWidth = 2;
			ctx.beginPath();
			ctx.moveTo(xLow, cy);
			ctx.lineTo(xQ1, cy);
			ctx.moveTo(xQ3, cy);
			ctx.lineTo(xHigh, cy);
			ctx.stroke();

			// Whisker caps
			ctx.beginPath();
			ctx.moveTo(xLow, cy - 8);
			ctx.lineTo(xLow, cy + 8);
			ctx.moveTo(xHigh, cy - 8);
			ctx.lineTo(xHigh, cy + 8);
			ctx.stroke();

			// Box (Q1-Q3)
			const gradient = ctx.createLinearGradient(xQ1, 0, xQ3, 0);
			gradient.addColorStop(0, '#3b82f6');
			gradient.addColorStop(1, '#93c5fd');
			ctx.fillStyle = gradient;
			ctx.strokeStyle = '#3b82f6';
			ctx.lineWidth = 1;
			ctx.beginPath();
			ctx.roundRect(xQ1, cy - boxH / 2, xQ3 - xQ1, boxH, 4);
			ctx.fill();
			ctx.stroke();

			// Median line
			ctx.strokeStyle = '#1e3a5f';
			ctx.lineWidth = 2.5;
			ctx.beginPath();
			ctx.moveTo(xMed, cy - boxH / 2);
			ctx.lineTo(xMed, cy + boxH / 2);
			ctx.stroke();

			// Labels
			ctx.fillStyle = '#64748b';
			ctx.font = '10px Inter, -apple-system, sans-serif';
			ctx.textAlign = 'start';
			ctx.fillText(fmtTokens(whiskerLow), xLow, cy + boxH / 2 + 14);
			ctx.textAlign = 'center';
			ctx.fillText(fmtTokens(q1), xQ1, cy - boxH / 2 - 6);
			ctx.font = 'bold 10px Inter, -apple-system, sans-serif';
			ctx.fillStyle = '#232326';
			ctx.fillText(fmtTokens(median), xMed, cy - boxH / 2 - 6);
			ctx.fillStyle = '#64748b';
			ctx.font = '10px Inter, -apple-system, sans-serif';
			ctx.fillText(fmtTokens(q3), xQ3, cy + boxH / 2 + 14);
			ctx.textAlign = 'end';
			ctx.fillText(fmtTokens(whiskerHigh), xHigh, cy + boxH / 2 + 14);

			ctx.restore();
		},
	};

	onMount(() => {
		chart = new Chart(canvas, {
			type: 'scatter',
			data: {
				datasets: [{
					data: [
						{ x: whiskerLow, y: 0 },
						{ x: q1, y: 0 },
						{ x: median, y: 0 },
						{ x: q3, y: 0 },
						{ x: whiskerHigh, y: 0 },
					],
					pointRadius: 0,
				}],
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				scales: {
					x: {
						display: false,
						min: whiskerLow * 0.95,
						max: whiskerHigh * 1.05,
					},
					y: { display: false },
				},
				plugins: {
					tooltip: { enabled: false },
				},
			},
			plugins: [boxPlotPlugin],
		});

		return () => {
			chart?.destroy();
			chart = null;
		};
	});
</script>

<div class="boxplot-wrap" style="height: {height}px">
	<canvas bind:this={canvas}></canvas>
</div>

<style>
	.boxplot-wrap {
		position: relative;
		width: 100%;
	}
</style>
