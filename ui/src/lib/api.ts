import type { SessionRead, SessionDetail, StatsResponse, DigestRead, DigestDetail } from './types';

const BASE = '/api/sessions';

async function fetchJSON<T>(url: string): Promise<T> {
	const res = await fetch(url);
	if (!res.ok) {
		throw new Error(`API error: ${res.status} ${res.statusText}`);
	}
	return res.json();
}

export async function getSessions(
	skip = 0, limit = 100, status?: string, userId?: string, projectName?: string
): Promise<SessionRead[]> {
	let url = `${BASE}/?skip=${skip}&limit=${limit}`;
	if (status) url += `&status=${status}`;
	if (userId) url += `&user_id=${encodeURIComponent(userId)}`;
	if (projectName) url += `&project_name=${encodeURIComponent(projectName)}`;
	return fetchJSON(url);
}

export async function getSession(id: string): Promise<SessionDetail> {
	return fetchJSON(`${BASE}/${id}`);
}

export async function getStats(): Promise<StatsResponse> {
	return fetchJSON(`${BASE}/stats`);
}

export async function triggerAnalysis(id: string): Promise<SessionDetail> {
	const res = await fetch(`${BASE}/${id}/analyze`, { method: 'POST' });
	if (!res.ok) throw new Error(`Analysis failed: ${res.status}`);
	return res.json();
}

// Digest API
export async function getDigests(project?: string): Promise<DigestRead[]> {
	let url = '/api/digests/';
	if (project) {
		url += `?project=${encodeURIComponent(project)}`;
	} else {
		url += '?global_only=true';
	}
	return fetchJSON(url);
}

export async function getDigest(id: string): Promise<DigestDetail> {
	return fetchJSON(`/api/digests/${id}`);
}

// Projects API
export interface ProjectRead {
	name: string;
	session_count: number;
	total_tokens: number;
	total_tool_calls: number;
	top_tools: string[];
	languages: string[];
	latest_session: string;
	has_digest: boolean;
}

export async function getProjects(): Promise<ProjectRead[]> {
	return fetchJSON('/api/projects/');
}

export async function tagSession(sessionId: string, projectName: string): Promise<void> {
	const res = await fetch(`/api/sessions/${sessionId}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ project_name: projectName }),
	});
	if (!res.ok) throw new Error(`Tag failed: ${res.status}`);
}

// Trends API
export interface TrendPoint {
	date: string;
	session_count: number;
	analyzed_count: number;
	total_tokens: number;
	total_tool_calls: number;
	avg_read_edit_ratio: number | null;
	avg_edits_without_read_pct: number | null;
	avg_error_rate: number | null;
	avg_research_mutation_ratio: number | null;
	avg_session_duration_ms: number | null;
	agent_distribution_json: string | null;
}

export interface BaselineRead {
	id: string;
	user_id: string;
	project_name: string | null;
	session_count: number;
	avg_turns: number;
	avg_tool_count: number;
	avg_read_edit_ratio: number;
	avg_error_rate: number;
	avg_duration_ms: number;
}

export async function getTrends(project?: string, userId?: string, days = 90): Promise<TrendPoint[]> {
	let url = `/api/trends/daily?days=${days}`;
	if (project) url += `&project=${encodeURIComponent(project)}`;
	if (userId) url += `&user_id=${encodeURIComponent(userId)}`;
	return fetchJSON(url);
}

export async function getBaselines(project?: string): Promise<BaselineRead[]> {
	let url = '/api/trends/baselines';
	if (project) url += `?project=${encodeURIComponent(project)}`;
	return fetchJSON(url);
}

// Users API
export interface UserSummary {
	user_id: string;
	display_name: string;
	session_count: number;
	analyzed_count: number;
	indexed_count: number;
	avg_read_edit_ratio: number | null;
	avg_edits_without_read_pct: number | null;
	avg_research_mutation_ratio: number | null;
	avg_write_vs_edit_pct: number | null;
	avg_error_rate: number | null;
	avg_repeated_edits: number | null;
	avg_subagent_spawn_rate: number | null;
	avg_tokens_per_useful_edit: number | null;
	avg_context_pressure: number | null;
	avg_turn_count: number | null;
	avg_tool_calls_per_turn: number | null;
	avg_duration_ms: number | null;
	total_tokens: number;
	projects: string[];
	agents: string[];
	sources: string[];
}

export async function getUsers(start?: string, end?: string, project?: string): Promise<UserSummary[]> {
	let url = '/api/users/';
	const params: string[] = [];
	if (start) params.push(`start=${start}`);
	if (end) params.push(`end=${end}`);
	if (project) params.push(`project=${encodeURIComponent(project)}`);
	if (params.length) url += `?${params.join('&')}`;
	return fetchJSON(url);
}
