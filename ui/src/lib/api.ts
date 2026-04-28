import type { SessionRead, SessionDetail, StatsResponse, DigestRead, DigestDetail, TaskRead } from './types';

const BASE = '/api/sessions';

async function fetchJSON<T>(url: string): Promise<T> {
	const res = await fetch(url);
	if (!res.ok) {
		throw new Error(`API error: ${res.status} ${res.statusText}`);
	}
	return res.json();
}

export async function getSessions(
	skip = 0, limit = 100, status?: string, userId?: string, projectName?: string, label?: string
): Promise<SessionRead[]> {
	let url = `${BASE}/?skip=${skip}&limit=${limit}`;
	if (status) url += `&status=${status}`;
	if (userId) url += `&user_id=${encodeURIComponent(userId)}`;
	if (projectName) url += `&project_name=${encodeURIComponent(projectName)}`;
	if (label) url += `&label=${encodeURIComponent(label)}`;
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
export async function getDigests(project?: string, userId?: string): Promise<DigestRead[]> {
	let url = '/api/digests/';
	const params: string[] = [];
	if (project) params.push(`project=${encodeURIComponent(project)}`);
	if (userId) params.push(`user_id=${encodeURIComponent(userId)}`);
	if (params.length) url += `?${params.join('&')}`;
	return fetchJSON(url);
}

export async function getDigest(id: string): Promise<DigestDetail> {
	return fetchJSON(`/api/digests/${id}`);
}

// Projects API
export interface ProjectRead {
	name: string;
	session_count: number;
	analyzed_count: number;
	developer_count: number;
	active_days: number;
	total_tokens: number;
	total_tool_calls: number;
	top_tools: string[];
	languages: string[];
	latest_session: string;
	has_digest: boolean;
	agents: Record<string, number>;
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

export interface TokenDistribution {
	q1: number;
	median: number;
	q3: number;
	whisker_low: number;
	whisker_high: number;
	max_val: number;
	count: number;
}

export async function getTokenDistribution(project?: string, userId?: string): Promise<TokenDistribution | null> {
	let url = '/api/trends/token-distribution';
	const params: string[] = [];
	if (project) params.push(`project=${encodeURIComponent(project)}`);
	if (userId) params.push(`user_id=${encodeURIComponent(userId)}`);
	if (params.length) url += `?${params.join('&')}`;
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

	// Token efficiency
	avg_efficiency_score: number | null;
	avg_tasks_per_session: number | null;
	total_tasks: number;
}

// Doctor API
export interface RefreshRunRead {
	id: string;
	command: string;
	started_at: string;
	completed_at: string | null;
	status: string;
	sessions_analyzed: number;
	digests_generated: number;
	total_prompt_tokens: number;
	total_completion_tokens: number;
	estimated_cost_usd: number | null;
	wall_seconds: number | null;
	db_size_bytes: number | null;
	error_message: string | null;
	metadata: Record<string, string | number | null> | null;
}

export interface DbSizePoint { timestamp: string; bytes: number; }

export interface ConfigLimit { key: string; value: number; description: string; }
export interface ConfigSnapshot { model: string; provider: string; limits: ConfigLimit[]; }

export interface SystemHealthResponse {
	total_sessions: number;
	indexed_sessions: number;
	analyzed_sessions: number;
	failed_sessions: number;
	total_projects: number;
	total_developers: number;
	db_size_bytes: number | null;
	db_size_history: DbSizePoint[];
	last_refresh: RefreshRunRead | null;
	last_analyze: RefreshRunRead | null;
	last_digest: RefreshRunRead | null;
	config: ConfigSnapshot;
}

export interface CommandCost { command: string; prompt_tokens: number; completion_tokens: number; estimated_cost_usd: number | null; run_count: number; }
export interface ProjectCost { project_name: string; prompt_tokens: number; completion_tokens: number; estimated_cost_usd: number | null; session_count: number; }
export interface DailyCost { date: string; prompt_tokens: number; completion_tokens: number; estimated_cost_usd: number | null; }

export interface CostSummaryResponse {
	total_prompt_tokens: number;
	total_completion_tokens: number;
	estimated_cost_usd: number | null;
	by_command: CommandCost[];
	by_project: ProjectCost[];
	daily_trend: DailyCost[];
}

export interface CallKindCost {
	call_kind: string;
	model: string;
	provider: string;
	call_count: number;
	success_count: number;
	failure_count: number;
	prompt_tokens: number;
	completion_tokens: number;
	cache_read_tokens: number;
	cache_write_tokens: number;
	total_duration_ms: number;
	avg_duration_ms: number;
	estimated_cost_usd: number | null;
}

export interface CallKindCostResponse {
	total_calls: number;
	total_cost_usd: number | null;
	total_prompt_tokens: number;
	total_completion_tokens: number;
	by_kind: CallKindCost[];
}

export interface CapabilityDescriptor {
	key: string;
	description: string;
}

export interface SourceCapabilities {
	name: string;
	capabilities: string[];
	missing: string[];
	session_count: number;
}

export interface MetricRequirement {
	id: string;
	requires: string[];
	available_on: string[];
	missing_on: string[];
}

export interface CapabilitiesResponse {
	capabilities: CapabilityDescriptor[];
	sources: SourceCapabilities[];
	metrics: MetricRequirement[];
}

export interface ProjectCoverage { project_name: string; total_sessions: number; indexed: number; analyzed: number; failed: number; coverage_pct: number; avg_interestingness: number | null; }
export interface ScoreBucket { bucket: string; count: number; }

export interface CoverageResponse {
	projects: ProjectCoverage[];
	score_distribution: ScoreBucket[];
}

export async function getDoctorHealth(): Promise<SystemHealthResponse> {
	return fetchJSON('/api/doctor/health');
}

export async function getDoctorRuns(command?: string, status?: string, skip = 0, limit = 50): Promise<RefreshRunRead[]> {
	const params: string[] = [`skip=${skip}`, `limit=${limit}`];
	if (command) params.push(`command=${command}`);
	if (status) params.push(`status=${status}`);
	return fetchJSON(`/api/doctor/runs?${params.join('&')}`);
}

export async function getDoctorCost(): Promise<CostSummaryResponse> {
	return fetchJSON('/api/doctor/cost');
}

export async function getDoctorCostByKind(): Promise<CallKindCostResponse> {
	return fetchJSON('/api/doctor/cost-by-kind');
}

export async function getDoctorCapabilities(): Promise<CapabilitiesResponse> {
	return fetchJSON('/api/doctor/capabilities');
}

export async function getDoctorCoverage(): Promise<CoverageResponse> {
	return fetchJSON('/api/doctor/coverage');
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

export async function getUserStats(userId: string): Promise<Record<string, unknown>> {
	return fetchJSON(`/api/users/${encodeURIComponent(userId)}/stats`);
}

export async function getProjectStats(projectName: string): Promise<Record<string, unknown>> {
	return fetchJSON(`/api/projects/${encodeURIComponent(projectName)}/stats`);
}

export async function getProjectThemes(projectName: string): Promise<import('./types').ThemeRead[]> {
	return fetchJSON(`/api/projects/${encodeURIComponent(projectName)}/themes`);
}

export async function getUserThemes(userId: string, limit = 50): Promise<import('./types').UserThemeRead[]> {
	return fetchJSON(`/api/users/${encodeURIComponent(userId)}/themes?limit=${limit}`);
}

export interface MoodQuote { quote: string; mood: string; project: string | null; session_id: string | null; }
export interface MoodGroup { mood: string; quotes: MoodQuote[]; }
export interface UserMoodResponse { user_id: string; total_sessions: number; sessions_with_quotes: number; mood_groups: MoodGroup[]; }

export async function getUserMoodQuotes(userId: string): Promise<UserMoodResponse> {
	return fetchJSON(`/api/users/${encodeURIComponent(userId)}/mood-quotes`);
}

// --- Tasks ---

export interface TaskListItem {
	id: string;
	session_id: string;
	task_number: number;
	name: string;
	description: string;
	start_turn: number;
	end_turn: number;
	turn_count: number;
	prompt_tokens_total: number;
	completion_tokens_total: number;
	estimated_waste_tokens: number | null;
	session_start_time: string | null;
	user_id: string | null;
	project_name: string | null;
}

export interface TaskStatsResponse {
	total_tasks: number;
	avg_turns_per_task: number;
	avg_tokens_per_task: number;
	top_task_names: Array<{ name: string; count: number }>;
}

export async function getTasks(
	skip = 0, limit = 50, userId?: string, projectName?: string, search?: string, sort = 'date'
): Promise<TaskListItem[]> {
	let url = `/api/tasks/?skip=${skip}&limit=${limit}&sort=${sort}`;
	if (userId) url += `&user_id=${encodeURIComponent(userId)}`;
	if (projectName) url += `&project_name=${encodeURIComponent(projectName)}`;
	if (search) url += `&search=${encodeURIComponent(search)}`;
	return fetchJSON(url);
}

export async function getTaskStats(userId?: string, projectName?: string): Promise<TaskStatsResponse> {
	let url = '/api/tasks/stats?';
	if (userId) url += `user_id=${encodeURIComponent(userId)}&`;
	if (projectName) url += `project_name=${encodeURIComponent(projectName)}&`;
	return fetchJSON(url);
}
