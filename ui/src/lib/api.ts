import type { SessionRead, SessionDetail, StatsResponse, DigestRead, DigestDetail } from './types';

const BASE = '/api/sessions';

async function fetchJSON<T>(url: string): Promise<T> {
	const res = await fetch(url);
	if (!res.ok) {
		throw new Error(`API error: ${res.status} ${res.statusText}`);
	}
	return res.json();
}

export async function getSessions(skip = 0, limit = 20, status?: string): Promise<SessionRead[]> {
	let url = `${BASE}/?skip=${skip}&limit=${limit}`;
	if (status) url += `&status=${status}`;
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
	if (project) url += `?project=${encodeURIComponent(project)}`;
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
