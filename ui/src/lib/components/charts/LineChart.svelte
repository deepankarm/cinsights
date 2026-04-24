<script lang="ts">
	import { onMount } from 'svelte';
	import { Chart, COLORS, TASK_COLORS } from './chartConfig';
	import type { ChartConfiguration, Chart as ChartType } from 'chart.js';

	export interface LineDataset {
		label: string;
		data: number[];
		color: string;
		fill?: boolean;
		yAxisID?: string;
	}

	export interface MarkerPoint {
		index: number;
		color: string;
		label?: string;
		/** Draw a vertical line at this index */
		verticalLine?: boolean;
	}

	export interface TaskBand {
		startIndex: number;
		endIndex: number;
		name: string;
		colorIndex: number;
	}

	export interface ReferenceLine {
		value: number;
		color: string;
		label?: string;
		yAxisID?: string;
	}

	let {
		labels,
		datasets,
		markers = [],
		taskBands = [],
		referenceLines = [],
		height = 360,
		yFormat = (v: number) => String(v),
		tooltipFormat = undefined,
		secondaryYFormat = undefined,
	}: {
		labels: string[];
		datasets: LineDataset[];
		markers?: MarkerPoint[];
		taskBands?: TaskBand[];
		referenceLines?: ReferenceLine[];
		height?: number;
		yFormat?: (v: number) => string;
		tooltipFormat?: (datasetIndex: number, index: number, value: number) => string;
		secondaryYFormat?: (v: number) => string;
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: ChartType | null = null;

	function buildConfig(): ChartConfiguration<'line'> {
		const hasSecondary = datasets.some(d => d.yAxisID === 'y1');

		const annotations: Record<string, unknown> = {};

		// Task bands
		for (let i = 0; i < taskBands.length; i++) {
			const band = taskBands[i];
			const bandColor = TASK_COLORS[band.colorIndex % TASK_COLORS.length];
			annotations[`band${i}`] = {
				type: 'box',
				xMin: band.startIndex,
				xMax: band.endIndex,
				backgroundColor: bandColor + '14', // ~8% opacity
				borderWidth: 0,
				label: {
					display: true,
					content: band.name.slice(0, 30),
					position: { x: 'start', y: 'end' },
					color: bandColor + '99',
					font: { size: 9 },
					rotation: -90,
					padding: 4,
				},
			};
		}

		// Reference lines
		for (let i = 0; i < referenceLines.length; i++) {
			const rl = referenceLines[i];
			annotations[`ref${i}`] = {
				type: 'line',
				yMin: rl.value,
				yMax: rl.value,
				yScaleID: rl.yAxisID ?? 'y',
				borderColor: rl.color,
				borderWidth: 1,
				borderDash: [4, 3],
				label: rl.label ? {
					display: true,
					content: rl.label,
					position: 'end',
					backgroundColor: 'transparent',
					color: rl.color,
					font: { size: 10 },
				} : undefined,
			};
		}

		return {
			type: 'line',
			data: {
				labels,
				datasets: datasets.map((ds, di) => {
					// Collect markers for this dataset
					const pointBackgroundColors = new Array(labels.length).fill('transparent');
					const pointBorderColors = new Array(labels.length).fill('transparent');
					const pointRadii = new Array(labels.length).fill(0);

					if (di === 0) {
						// markers apply to first dataset by default
						for (const m of markers) {
							pointBackgroundColors[m.index] = m.color;
							pointBorderColors[m.index] = 'white';
							pointRadii[m.index] = 3.5;
						}
					}

					return {
						label: ds.label,
						data: ds.data,
						borderColor: ds.color,
						borderWidth: 1.5,
						backgroundColor: ds.fill ? createGradient(ds.color) : 'transparent',
						fill: ds.fill ?? false,
						tension: 0.1,
						pointRadius: pointRadii,
						pointBackgroundColor: pointBackgroundColors,
						pointBorderColor: pointBorderColors,
						pointBorderWidth: 1.5,
						pointHoverRadius: 4,
						pointHoverBackgroundColor: ds.color,
						pointHoverBorderColor: 'white',
						pointHoverBorderWidth: 2,
						yAxisID: ds.yAxisID ?? 'y',
					};
				}),
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: {
					mode: 'index',
					intersect: false,
				},
				scales: {
					x: {
						grid: { display: false },
						ticks: { font: { size: 10 }, maxRotation: 0, autoSkipPadding: 20 },
					},
					y: {
						grid: { color: '#f1f5f9' },
						ticks: {
							font: { size: 10 },
							callback: (v) => yFormat(v as number),
						},
					},
					...(hasSecondary ? {
						y1: {
							position: 'right' as const,
							grid: { display: false },
							ticks: {
								font: { size: 10 },
								callback: (v) => secondaryYFormat ? secondaryYFormat(v as number) : String(v),
							},
						},
					} : {}),
				},
				plugins: {
					tooltip: {
						callbacks: {
							label: (ctx) => {
								const val = ctx.parsed.y as number;
								if (tooltipFormat) {
									return tooltipFormat(ctx.datasetIndex, ctx.dataIndex, val);
								}
								const ds = datasets[ctx.datasetIndex];
								return `${ds.label}: ${yFormat(val)}`;
							},
						},
					},
					annotation: {
						annotations: annotations as never,
					},
				},
			},
		};
	}

	function createGradient(color: string): CanvasGradient | string {
		if (!canvas) return color;
		const ctx = canvas.getContext('2d');
		if (!ctx) return color;
		const gradient = ctx.createLinearGradient(0, 0, 0, height);
		gradient.addColorStop(0, color + '40'); // 25% opacity
		gradient.addColorStop(1, color + '00'); // 0% opacity
		return gradient;
	}

	// Add vertical line markers via a custom plugin
	const verticalLinePlugin = {
		id: 'verticalLineMarkers',
		afterDatasetsDraw(chartInstance: ChartType) {
			if (!markers.length) return;
			const ctx = chartInstance.ctx;
			const xScale = chartInstance.scales['x'];
			const yScale = chartInstance.scales['y'];
			if (!xScale || !yScale) return;

			for (const m of markers) {
				if (!m.verticalLine) continue;
				const x = xScale.getPixelForValue(m.index);
				ctx.save();
				ctx.beginPath();
				ctx.moveTo(x, yScale.top);
				ctx.lineTo(x, yScale.bottom);
				ctx.strokeStyle = m.color + '66';
				ctx.lineWidth = 1;
				ctx.stroke();
				ctx.restore();
			}
		},
	};

	onMount(() => {
		const config = buildConfig();
		// Register vertical line plugin locally
		config.plugins = [verticalLinePlugin];
		chart = new Chart(canvas, config);

		return () => {
			chart?.destroy();
			chart = null;
		};
	});

	// Reactively update when data changes
	$effect(() => {
		// Access reactive deps
		void labels;
		void datasets;
		void markers;
		void taskBands;
		void referenceLines;

		if (chart) {
			chart.destroy();
			const config = buildConfig();
			config.plugins = [verticalLinePlugin];
			chart = new Chart(canvas, config);
		}
	});
</script>

<div class="line-chart-wrap" style="height: {height}px">
	<canvas bind:this={canvas}></canvas>
</div>

<style>
	.line-chart-wrap {
		position: relative;
		width: 100%;
	}
</style>
