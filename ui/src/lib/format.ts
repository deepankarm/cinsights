export function fmtDur(ms: number | null): string {
	if (!ms) return '-';
	const mins = Math.floor(ms / 60000);
	if (mins >= 60) return `${(mins / 60).toFixed(1)}h`;
	return `${mins}m`;
}

export function fmtTokens(n: number): string {
	if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
	if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
	return n.toString();
}

export function fmtNum(v: number | null, suffix = ''): string {
	if (v == null) return '-';
	return v.toFixed(1) + suffix;
}

export function fmtDate(iso: string): string {
	// Server stores UTC timestamps without Z suffix — treat as UTC
	const ts = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
	const d = new Date(ts);
	const day = d.getDate().toString().padStart(2, '0');
	const mon = d.toLocaleString('en', { month: 'short' });
	const h = d.getHours().toString().padStart(2, '0');
	const m = d.getMinutes().toString().padStart(2, '0');
	return `${day} ${mon} ${h}:${m}`;
}

export function fmtDuration(start: string, end: string | null): string {
	if (!end) return '-';
	const ms = new Date(end).getTime() - new Date(start).getTime();
	if (ms < 1000) return '<1s';
	const secs = Math.floor(ms / 1000);
	const mins = Math.floor(secs / 60);
	const hrs = Math.floor(mins / 60);
	const days = Math.floor(hrs / 24);
	if (days > 0) return `${days}d ${hrs % 24}h`;
	if (hrs > 0) return `${hrs}h ${mins % 60}m`;
	if (mins > 0) return `${mins}m ${secs % 60}s`;
	return `${secs % 60}s`;
}

export function fmtDateRange(start: string, end: string | null): string {
	const s = fmtDate(start);
	if (!end) return s;
	const ts1 = start.endsWith('Z') || start.includes('+') ? start : start + 'Z';
	const ts2 = end.endsWith('Z') || end.includes('+') ? end : end + 'Z';
	const d1 = new Date(ts1);
	const d2 = new Date(ts2);
	// Same calendar day — just show start
	if (d1.toDateString() === d2.toDateString()) return s;
	return `${s} → ${fmtDate(end)}`;
}

export function fmtMinutes(m: number): string {
	if (m >= 1440) return `${(m / 1440).toFixed(1)}d`;
	if (m >= 60) return `${(m / 60).toFixed(1)}h`;
	return `${m.toFixed(0)}m`;
}

export function barPct(value: number, max: number): number {
	return Math.max(3, (value / max) * 100);
}

export function maxVal(obj: Record<string, number>): number {
	return Math.max(...Object.values(obj), 1);
}

export function gradeColor(grade: string): string {
	switch (grade) {
		case 'A': return '#10b981';
		case 'B': return '#84cc16';
		case 'C': return '#eab308';
		case 'D': return '#f97316';
		case 'F': return '#ef4444';
		default: return '#a1a1aa';
	}
}

export function gradeBg(grade: string): string {
	switch (grade) {
		case 'A': return '#ecfdf5';
		case 'B': return '#f7fee7';
		case 'C': return '#fefce8';
		case 'D': return '#fff7ed';
		case 'F': return '#fef2f2';
		default: return '#f4f4f5';
	}
}

export function copyText(text: string, btn: HTMLButtonElement): void {
	navigator.clipboard.writeText(text).then(() => {
		const orig = btn.textContent;
		btn.textContent = 'Copied!';
		setTimeout(() => { btn.textContent = orig; }, 2000);
	});
}

export function fmtBytes(n: number): string {
	if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} GB`;
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
	if (n >= 1_000) return `${(n / 1_000).toFixed(0)} KB`;
	return `${n} B`;
}

export function fmtCost(usd: number | null): string {
	if (usd == null) return '-';
	if (usd < 0.01) return `$${usd.toFixed(4)}`;
	return `$${usd.toFixed(2)}`;
}

export function fmtAgo(iso: string): string {
	// Server stores UTC timestamps without Z suffix — treat as UTC
	const ts = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
	const ms = Date.now() - new Date(ts).getTime();
	const mins = Math.floor(ms / 60000);
	if (mins < 1) return 'just now';
	if (mins < 60) return `${mins}m ago`;
	const hrs = Math.floor(mins / 60);
	if (hrs < 24) return `${hrs}h ago`;
	const days = Math.floor(hrs / 24);
	return `${days}d ago`;
}

export function fmtSecs(s: number | null): string {
	if (s == null) return '-';
	if (s < 60) return `${s.toFixed(0)}s`;
	if (s < 3600) return `${(s / 60).toFixed(1)}min`;
	return `${(s / 3600).toFixed(1)}h`;
}

const avatarColors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#ef4444', '#6366f1'];
export function avatarColor(name: string): string {
	let h = 0;
	for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
	return avatarColors[Math.abs(h) % avatarColors.length];
}

export type QualityMetric = { label: string; value: string; teamAvg?: string; deltaColor?: string; deltaAbove?: boolean };

type MetricField = { key: string; label: string; suffix: string; higherIs?: 'better' | 'worse'; fmt?: (v: number) => string };
const METRIC_FIELDS: MetricField[] = [
	{ key: 'avg_read_edit_ratio', label: 'Read:Edit', suffix: '', higherIs: 'better' },
	{ key: 'avg_edits_without_read_pct', label: 'Blind edits', suffix: '%', higherIs: 'worse' },
	{ key: 'avg_research_mutation_ratio', label: 'Research:Mut', suffix: '' , higherIs: 'better' },
	{ key: 'avg_error_rate', label: 'Error rate', suffix: '%', higherIs: 'worse' },
	{ key: 'avg_write_vs_edit_pct', label: 'Write vs Edit', suffix: '%', higherIs: 'worse' },
	{ key: 'avg_repeated_edits', label: 'Thrashing', suffix: '', higherIs: 'worse' },
	{ key: 'avg_subagent_spawn_rate', label: 'Subagents', suffix: '%' },
	{ key: 'avg_context_pressure', label: 'Ctx pressure', suffix: '', higherIs: 'worse' },
	{ key: 'avg_tool_calls_per_turn', label: 'Tools/turn', suffix: '' },
	{ key: 'avg_duration_ms', label: 'Avg duration', suffix: '', fmt: (v: number) => fmtDur(v) },
];

export function userQualityMetrics(user: Record<string, unknown>, teamAvgs?: Record<string, number | null>): QualityMetric[] {
	return METRIC_FIELDS.map(f => {
		const v = user[f.key] as number | null;
		const result: QualityMetric = { label: f.label, value: f.fmt ? f.fmt(v ?? 0) : fmtNum(v, f.suffix) };
		if (teamAvgs && v != null) {
			const avg = teamAvgs[f.key];
			if (avg != null && avg !== 0) {
				result.teamAvg = f.fmt ? f.fmt(avg) : fmtNum(avg, f.suffix);
				const pct = Math.abs((v - avg) / avg) * 100;
				if (pct > 15 && f.higherIs) {
					const above = v > avg;
					const isGood = f.higherIs === 'better' ? above : !above;
					result.deltaColor = isGood ? '#16a34a' : '#dc2626';
					result.deltaAbove = above;
				}
			}
		}
		return result;
	});
}

export function aggregateQualityMetrics(users: Record<string, unknown>[]): QualityMetric[] {
	return METRIC_FIELDS.map(f => {
		let weightedSum = 0, totalWeight = 0;
		for (const u of users) {
			const v = u[f.key] as number | null;
			const w = (u['analyzed_count'] as number) || 1;
			if (v != null) { weightedSum += v * w; totalWeight += w; }
		}
		const avg = totalWeight > 0 ? weightedSum / totalWeight : null;
		return { label: f.label, value: f.fmt ? f.fmt(avg ?? 0) : fmtNum(avg, f.suffix) };
	});
}
