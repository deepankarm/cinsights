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
		xAxisID?: string;
		/** Render as low-opacity bars instead of a line (horizontal mode only) */
		barMode?: boolean;
	}

	export interface MarkerPoint {
		index: number;
		color: string;
		label?: string;
		/** Draw a line across the chart at this index */
		verticalLine?: boolean;
	}

	export interface TaskBand {
		startIndex: number;
		endIndex: number;
		name: string;
		description?: string;
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
		horizontal = false,
		yFormat = (v: number) => String(v),
		tooltipFormat = undefined,
		secondaryYFormat = undefined,
		secondaryXFormat = undefined,
	}: {
		labels: string[];
		datasets: LineDataset[];
		markers?: MarkerPoint[];
		taskBands?: TaskBand[];
		referenceLines?: ReferenceLine[];
		height?: number;
		horizontal?: boolean;
		yFormat?: (v: number) => string;
		tooltipFormat?: (datasetIndex: number, index: number, value: number) => string;
		secondaryYFormat?: (v: number) => string;
		secondaryXFormat?: (v: number) => string;
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: ChartType | null = null;

	function buildConfig(): ChartConfiguration {
		const annotations: Record<string, unknown> = {};

		if (horizontal) {
			return buildHorizontalConfig(annotations);
		}
		return buildVerticalConfig(annotations);
	}

	function buildVerticalConfig(annotations: Record<string, unknown>): ChartConfiguration<'line'> {
		const hasSecondary = datasets.some(d => d.yAxisID === 'y1');

		// Task bands (vertical: x-axis bands)
		for (let i = 0; i < taskBands.length; i++) {
			const band = taskBands[i];
			const bandColor = TASK_COLORS[band.colorIndex % TASK_COLORS.length];
			annotations[`band${i}`] = {
				type: 'box',
				xMin: band.startIndex,
				xMax: band.endIndex,
				backgroundColor: bandColor + '14',
				borderWidth: 0,
				label: {
					display: true,
					content: band.name,
					position: { x: 'start', y: 'start' },
					color: bandColor,
					font: { size: 10, weight: 'bold' },
					padding: { top: 4, left: 6 },
				},
			};
			annotations[`bandBorder${i}`] = {
				type: 'line',
				xMin: band.startIndex,
				xMax: band.startIndex,
				borderColor: bandColor + '33',
				borderWidth: 1,
				borderDash: [3, 3],
			};
		}

		// Reference lines
		for (let i = 0; i < referenceLines.length; i++) {
			const rl = referenceLines[i];
			annotations[`ref${i}`] = {
				type: 'line',
				yMin: rl.value, yMax: rl.value,
				yScaleID: rl.yAxisID ?? 'y',
				borderColor: rl.color, borderWidth: 1, borderDash: [4, 3],
				label: rl.label ? {
					display: true, content: rl.label, position: 'end',
					backgroundColor: 'transparent', color: rl.color, font: { size: 10 },
				} : undefined,
			};
		}

		return {
			type: 'line',
			data: {
				labels,
				datasets: datasets.map((ds, di) => {
					const pointBg = new Array(labels.length).fill('transparent');
					const pointBorder = new Array(labels.length).fill('transparent');
					const pointRadii = new Array(labels.length).fill(0);
					if (di === 0) {
						for (const m of markers) {
							pointBg[m.index] = m.color;
							pointBorder[m.index] = 'white';
							pointRadii[m.index] = 3.5;
						}
					}
					return {
						label: ds.label, data: ds.data,
						borderColor: ds.color, borderWidth: 1.5,
						backgroundColor: ds.fill ? createGradientVertical(ds.color) : 'transparent',
						fill: ds.fill ?? false, tension: 0.1,
						pointRadius: pointRadii, pointBackgroundColor: pointBg,
						pointBorderColor: pointBorder, pointBorderWidth: 1.5,
						pointHoverRadius: 4, pointHoverBackgroundColor: ds.color,
						pointHoverBorderColor: 'white', pointHoverBorderWidth: 2,
						yAxisID: ds.yAxisID ?? 'y',
					};
				}),
			},
			options: {
				responsive: true, maintainAspectRatio: false,
				interaction: { mode: 'index', intersect: false },
				scales: {
					x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkipPadding: 20 } },
					y: { grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 }, callback: (v) => yFormat(v as number) } },
					...(hasSecondary ? {
						y1: { position: 'right' as const, grid: { display: false },
							ticks: { font: { size: 10 }, callback: (v) => secondaryYFormat ? secondaryYFormat(v as number) : String(v) } },
					} : {}),
				},
				plugins: {
					tooltip: { callbacks: { label: (ctx) => {
						const val = ctx.parsed.y as number;
						if (tooltipFormat) return tooltipFormat(ctx.datasetIndex, ctx.dataIndex, val);
						return `${datasets[ctx.datasetIndex].label}: ${yFormat(val)}`;
					} } },
					annotation: { clip: false, annotations: annotations as never },
				},
			},
		};
	}

	function buildHorizontalConfig(annotations: Record<string, unknown>): ChartConfiguration {
		// Horizontal line chart: turns on y-axis (top→bottom), tokens on x-axis
		// Reads like a timeline — turn 1 at top, last turn at bottom

		const ds = datasets[0];

		// Task band annotations (horizontal boxes spanning turn ranges)
		for (let i = 0; i < taskBands.length; i++) {
			const band = taskBands[i];
			const bandColor = TASK_COLORS[band.colorIndex % TASK_COLORS.length];
			// Background band
			annotations[`band${i}`] = {
				type: 'box',
				yMin: band.startIndex,
				yMax: band.endIndex,
				backgroundColor: bandColor + '18',
				borderWidth: 0,
			};
			// Separator line at band start (skip first band)
			if (band.startIndex > 0) {
				annotations[`bandSep${i}`] = {
					type: 'line',
					yMin: band.startIndex - 0.5,
					yMax: band.startIndex - 0.5,
					borderColor: '#64748b',
					borderWidth: 1,
					borderDash: [4, 3],
				};
			}
			// Task name label centered vertically in the band
			const midIdx = Math.round((band.startIndex + band.endIndex) / 2);
			annotations[`bandLabel${i}`] = {
				type: 'label',
				xValue: 0,
				yValue: midIdx,
				xAdjust: 6,
				position: { x: 'start' },
				content: band.name,
				color: bandColor,
				font: { size: 10, weight: 'bold' },
				backgroundColor: 'white',
				backgroundShadowColor: 'rgba(0,0,0,0.08)',
				shadowBlur: 4,
				padding: { top: 2, bottom: 2, left: 6, right: 6 },
				borderRadius: 3,
			};
		}

		// Reference lines (vertical on x-axis)
		for (let i = 0; i < referenceLines.length; i++) {
			const rl = referenceLines[i];
			annotations[`ref${i}`] = {
				type: 'line',
				xMin: rl.value, xMax: rl.value,
				xScaleID: rl.yAxisID ?? 'x',
				borderColor: rl.color, borderWidth: 1, borderDash: [4, 3],
				label: rl.label ? {
					display: true, content: rl.label, position: 'start',
					backgroundColor: 'transparent', color: rl.color, font: { size: 9 },
				} : undefined,
			};
		}

		const hasSecondaryX = datasets.some(d => d.xAxisID === 'x1');

		const hasBars = datasets.some(d => d.barMode);

		return {
			type: hasBars ? 'bar' as const : 'line' as const,
			data: {
				labels,
				datasets: datasets.map((ds, di) => {
					if (ds.barMode) {
						// Low-opacity bars behind the line
						return {
							type: 'bar' as const,
							label: ds.label,
							data: ds.data,
							backgroundColor: ds.color + '18',
							borderWidth: 0,
							borderSkipped: false,
							barPercentage: 1.0,
							categoryPercentage: 1.0,
							xAxisID: ds.xAxisID ?? 'x',
							order: 1, // draw bars behind line
						};
					}
					// Line dataset
					const pointBg = new Array(labels.length).fill('transparent');
					const pointBorder = new Array(labels.length).fill('transparent');
					const pointRadii = new Array(labels.length).fill(0);
					if (di === 0) {
						for (const m of markers) {
							pointBg[m.index] = m.color;
							pointBorder[m.index] = 'white';
							pointRadii[m.index] = 3.5;
						}
					}
					return {
						type: 'line' as const,
						label: ds.label,
						data: ds.data,
						borderColor: ds.color,
						borderWidth: 1.5,
						backgroundColor: ds.fill ? createGradientHorizontal(ds.color) : 'transparent',
						fill: ds.fill ?? false,
						tension: 0.15,
						pointRadius: pointRadii,
						pointBackgroundColor: pointBg,
						pointBorderColor: pointBorder,
						pointBorderWidth: 1.5,
						pointHoverRadius: 4,
						pointHoverBackgroundColor: ds.color,
						pointHoverBorderColor: 'white',
						pointHoverBorderWidth: 2,
						xAxisID: ds.xAxisID ?? 'x',
						order: 0, // draw line on top
					};
				}),
			},
			options: {
				responsive: true, maintainAspectRatio: false,
				layout: { padding: { bottom: 40 } },
				indexAxis: 'y',
				interaction: { mode: 'index', intersect: false, axis: 'y' },
				scales: {
					x: {
						position: 'top',
						grid: { color: '#f1f5f9' },
						ticks: { font: { size: 10 }, callback: (v) => yFormat(v as number) },
						title: hasSecondaryX ? { display: true, text: 'Context Window', font: { size: 11, weight: 'bold' }, color: '#6366f1', padding: { bottom: 4 } } : undefined,
					},
					...(hasSecondaryX ? {
						x1: {
							position: 'bottom' as const,
							grid: { display: false },
							title: { display: true, text: 'Turn Duration', font: { size: 11, weight: 'bold' }, color: '#10b981', padding: { top: 4 } },
							ticks: {
								font: { size: 10 },
								color: '#10b981',
								callback: (v) => secondaryXFormat ? secondaryXFormat(v as number) : String(v),
							},
						},
					} : {}),
					y: {
						reverse: false,
						grid: { display: false },
						ticks: {
							font: { size: 9 },
							color: '#94a3b8',
							autoSkip: false,
							autoSkipPadding: 2,
						},
					},
				},
				plugins: {
					legend: { display: false },
					tooltip: { callbacks: { label: (ctx) => {
						const val = ctx.parsed.x as number;
						if (tooltipFormat) return tooltipFormat(ctx.datasetIndex, ctx.dataIndex, val);
						const fmt = ctx.dataset.xAxisID === 'x1' && secondaryXFormat ? secondaryXFormat : yFormat;
						return `${datasets[ctx.datasetIndex].label}: ${fmt(val)}`;
					} } },
					annotation: { clip: false, annotations: annotations as never },
				},
			},
		};
	}

	function createGradientHorizontal(color: string): CanvasGradient | string {
		if (!canvas) return color;
		const ctx = canvas.getContext('2d');
		if (!ctx) return color;
		const gradient = ctx.createLinearGradient(0, 0, canvas.width || 800, 0);
		gradient.addColorStop(0, color + '00');
		gradient.addColorStop(1, color + '40');
		return gradient;
	}

	function createGradientVertical(color: string): CanvasGradient | string {
		if (!canvas) return color;
		const ctx = canvas.getContext('2d');
		if (!ctx) return color;
		const gradient = ctx.createLinearGradient(0, 0, 0, height);
		gradient.addColorStop(0, color + '40');
		gradient.addColorStop(1, color + '00');
		return gradient;
	}

	// Custom plugin: marker lines (vertical in normal mode, horizontal in horizontal mode)
	const markerLinePlugin = {
		id: 'markerLines',
		afterDatasetsDraw(chartInstance: ChartType) {
			if (!markers.length) return;
			const ctx = chartInstance.ctx;
			const xScale = chartInstance.scales['x'];
			const yScale = chartInstance.scales['y'];
			if (!xScale || !yScale) return;

			for (const m of markers) {
				if (!m.verticalLine) continue;
				ctx.save();
				ctx.beginPath();
				if (horizontal) {
					const y = yScale.getPixelForValue(m.index);
					ctx.moveTo(xScale.left, y);
					ctx.lineTo(xScale.right, y);
				} else {
					const x = xScale.getPixelForValue(m.index);
					ctx.moveTo(x, yScale.top);
					ctx.lineTo(x, yScale.bottom);
				}
				ctx.strokeStyle = m.color + '66';
				ctx.lineWidth = 1;
				ctx.stroke();
				ctx.restore();
			}
		},
	};

	// Custom plugin: task band hover tooltip showing description
	let bandTooltip: { x: number; y: number; name: string; desc: string; color: string } | null = $state(null);

	const taskBandTooltipPlugin = {
		id: 'taskBandTooltip',
		afterEvent(chartInstance: ChartType, args: { event: { type: string; x: number | null; y: number | null } }) {
			if (!taskBands.length) return;
			const { type, x: mx, y: my } = args.event;

			if (type === 'mouseout' || mx == null || my == null) {
				bandTooltip = null;
				return;
			}
			if (type !== 'mousemove') return;

			const xScale = chartInstance.scales['x'];
			const yScale = chartInstance.scales['y'];
			if (!xScale || !yScale) return;

			if (horizontal) {
				// In horizontal mode, labels are on the left — detect hover near the left edge of each band
				const labelZoneRight = xScale.left;
				if (mx > labelZoneRight + 10) {
					bandTooltip = null;
					return;
				}
				for (let i = 0; i < taskBands.length; i++) {
					const band = taskBands[i];
					if (!band.description) continue;
					const y1 = yScale.getPixelForValue(band.startIndex - 0.5);
					const y2 = yScale.getPixelForValue(band.endIndex + 0.5);
					const top = Math.min(y1, y2);
					const bottom = Math.max(y1, y2);
					if (my >= top && my <= bottom) {
						const color = TASK_COLORS[band.colorIndex % TASK_COLORS.length];
						bandTooltip = { x: labelZoneRight + 12, y: top, name: band.name, desc: band.description, color };
						return;
					}
				}
			} else {
				// Vertical mode: labels at top of chart
				const labelZoneBottom = yScale.top + 24;
				if (my > labelZoneBottom) {
					bandTooltip = null;
					return;
				}
				for (let i = 0; i < taskBands.length; i++) {
					const band = taskBands[i];
					if (!band.description) continue;
					const x1 = xScale.getPixelForValue(band.startIndex);
					const x2 = xScale.getPixelForValue(band.endIndex);
					if (mx >= x1 && mx <= x2) {
						const color = TASK_COLORS[band.colorIndex % TASK_COLORS.length];
						bandTooltip = { x: mx, y: labelZoneBottom + 4, name: band.name, desc: band.description, color };
						return;
					}
				}
			}
			bandTooltip = null;
		},
	};

	const plugins = [markerLinePlugin, taskBandTooltipPlugin];

	onMount(() => {
		chart = new Chart(canvas, { ...buildConfig(), plugins });
		return () => { chart?.destroy(); chart = null; };
	});

	$effect(() => {
		void labels; void datasets; void markers; void taskBands; void referenceLines; void horizontal;
		if (chart) {
			chart.destroy();
			chart = new Chart(canvas, { ...buildConfig(), plugins });
		}
	});
</script>

<div class="line-chart-wrap" style="height: {height}px">
	<canvas bind:this={canvas}></canvas>
	{#if bandTooltip}
		<div class="band-tooltip" style="left: {bandTooltip.x}px; top: {bandTooltip.y}px; border-color: {bandTooltip.color}">
			<div class="band-tooltip-name" style="color: {bandTooltip.color}">{bandTooltip.name}</div>
			<div class="band-tooltip-desc">{bandTooltip.desc}</div>
		</div>
	{/if}
</div>

<style>
	.line-chart-wrap {
		position: relative;
		width: 100%;
	}
	.band-tooltip {
		position: absolute;
		z-index: 10;
		background: white;
		border: 1px solid;
		border-radius: 8px;
		padding: 8px 12px;
		max-width: 300px;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
		pointer-events: none;
	}
	.band-tooltip-name {
		font-size: 12px;
		font-weight: 700;
		margin-bottom: 3px;
	}
	.band-tooltip-desc {
		font-size: 11px;
		color: #64748b;
		line-height: 1.4;
	}
</style>
