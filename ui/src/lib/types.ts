export interface SessionRead {
	id: string;
	session_id: string | null;
	user_id: string | null;
	project_name: string | null;
	agent_type: string | null;
	source: string | null;
	start_time: string;
	end_time: string | null;
	model: string | null;
	total_tokens: number;
	status: 'indexed' | 'pending' | 'analyzed' | 'failed';
	tool_call_count: number;
	error_count: number;
	insight_count: number;
	active_duration_ms: number | null;
	interrupt_count: number | null;
	agent_version: string | null;
	effort_level: string | null;
}

export interface ToolCallRead {
	id: string;
	tool_name: string;
	input_value: string | null;
	output_value: string | null;
	duration_ms: number | null;
	success: boolean;
	timestamp: string;
}

export interface InsightRead {
	id: string;
	category: 'summary' | 'friction' | 'win' | 'recommendation' | 'pattern' | 'skill_proposal';
	label: string | null;
	title: string;
	content: string;
	severity: 'info' | 'warning' | 'critical';
	created_at: string;
}


export interface SessionDetail {
	id: string;
	session_id: string | null;
	user_id: string | null;
	project_name: string | null;
	start_time: string;
	end_time: string | null;
	model: string | null;
	total_tokens: number;
	prompt_tokens: number;
	completion_tokens: number;
	context_growth: Array<{ turn: number; prompt_tokens: number; completion_tokens: number; duration_ms?: number; interrupted?: boolean }> | null;
	status: string;
	tool_calls: ToolCallRead[];
	total_tool_calls: number;
	insights: InsightRead[];
	notable_quotes: Array<{ quote: string; mood?: string; vibe?: string }> | null;
	interrupt_count: number | null;
	agent_version: string | null;
	effort_level: string | null;
	adaptive_thinking_disabled: boolean | null;

	// Quality metrics
	read_edit_ratio: number | null;
	edits_without_read_pct: number | null;
	error_rate: number | null;
	repeated_edits_count: number | null;
	tokens_per_useful_edit: number | null;
	context_pressure_score: number | null;

	// Token efficiency signals
	error_retry_sequences: number | null;
	context_resets: number | null;
	duplicate_read_count: number | null;

	// Baseline averages for comparison
	baseline: {
		avg_read_edit_ratio: number;
		avg_edits_without_read_pct: number;
		avg_error_rate: number;
	} | null;
}

export interface StatsResponse {
	total_sessions: number;
	analyzed_sessions: number;
	total_insights: number;
	total_tool_calls: number;
	distinct_tool_count: number;
	top_tools: Record<string, number>;
	insight_counts: Record<string, number>;
}

export interface DigestRead {
	id: string;
	user_id: string | null;
	project_name: string | null;
	period_start: string;
	period_end: string;
	session_count: number;
	status: string;
	created_at: string;
	completed_at: string | null;
	sessions_since: number;
}

export interface DigestSectionRead {
	id: string;
	section_type: string;
	title: string;
	content: string;
	order: number;
	metadata: unknown;
}

export interface DigestDetail {
	id: string;
	user_id: string | null;
	project_name: string | null;
	period_start: string;
	period_end: string;
	session_count: number;
	status: string;
	stats: DigestStatsData | null;
	sections: DigestSectionRead[];
	analysis_prompt_tokens: number;
	analysis_completion_tokens: number;
	analysis_model: string | null;
	created_at: string;
	completed_at: string | null;
	sessions_since: number;
}

export interface WeeklyTrend {
	week: string;
	session_count: number;
	avg_read_edit_ratio: number | null;
	avg_edits_without_read_pct: number | null;
	avg_error_rate: number | null;
	avg_research_mutation_ratio: number | null;
	avg_write_vs_edit_pct: number | null;
	avg_context_pressure: number | null;
	total_tokens: number;
}

export interface DigestStatsData {
	session_count: number;
	analyzed_count: number;
	total_tool_calls: number;
	total_tokens: number;
	total_duration_minutes: number;
	active_days: number;
	tool_distribution: Record<string, number>;
	error_types: Record<string, number>;
	error_breakdown: Record<string, number>;
	language_distribution: Record<string, number>;
	time_of_day: Record<string, number>;
	session_health: Array<{
		session_id: string;
		start_time: string;
		duration_minutes: number;
		tool_count: number;
		error_count: number;
		total_tokens: number;
		grade: string;
		model: string | null;
	}>;
	tokens_per_session: Array<{ session_id: string; tokens: number; start_time: string }>;
	overlapping_sessions: Array<{ session_ids: string[]; overlap_minutes: number }>;
	permission_stats: {
		count: number;
		total_wait_seconds: number;
		avg_wait_seconds: number;
		max_wait_seconds: number;
	};
	plan_mode_stats: {
		entries: number;
		total_duration_seconds: number;
		plan_agent_count: number;
		plan_agent_tokens: number;
	};
	has_claude_md: boolean;
	weekly_trends: WeeklyTrend[];
	analysis_tokens_used: number;
	insight_labels: Record<string, number> | null;
	label_categories: Record<string, string> | null;
	label_trends: Array<{ date: string; labels: Record<string, number> }> | null;
	session_summaries: Array<{
		session_id: string;
		start_time: string;
		duration_min: number;
		summary: string;
	}>;
}
