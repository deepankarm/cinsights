import { Chart, registerables } from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';

Chart.register(...registerables, annotationPlugin);

// Global defaults matching cinsights design
Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = '#94a3b8';
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = 'white';
Chart.defaults.plugins.tooltip.titleColor = '#0f172a';
Chart.defaults.plugins.tooltip.bodyColor = '#64748b';
Chart.defaults.plugins.tooltip.borderColor = '#e2e8f0';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.boxPadding = 4;
Chart.defaults.scale.grid.color = '#f1f5f9';
(Chart.defaults.scale as Record<string, unknown>)['border'] = { display: false };

export const COLORS = {
	indigo: '#6366f1',
	green: '#10b981',
	amber: '#f59e0b',
	red: '#ef4444',
	purple: '#8b5cf6',
	blue: '#3b82f6',
	cyan: '#06b6d4',
	pink: '#ec4899',
	teal: '#14b8a6',
	orange: '#f97316',
	lime: '#84cc16',
} as const;

export const TASK_COLORS = [
	COLORS.indigo, COLORS.green, COLORS.amber, COLORS.red,
	COLORS.purple, COLORS.pink, COLORS.teal, COLORS.orange,
	COLORS.blue, COLORS.lime,
];

export { Chart };
