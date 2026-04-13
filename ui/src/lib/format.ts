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
	const d = new Date(iso);
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
	const mins = Math.floor(ms / 60000);
	const secs = Math.floor((ms % 60000) / 1000);
	if (mins > 0) return `${mins}m ${secs}s`;
	return `${secs}s`;
}

const avatarColors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#ef4444', '#6366f1'];
export function avatarColor(name: string): string {
	let h = 0;
	for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
	return avatarColors[Math.abs(h) % avatarColors.length];
}
