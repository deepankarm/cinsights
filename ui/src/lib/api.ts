import type { SessionRead, SessionDetail, StatsResponse } from './types';

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
