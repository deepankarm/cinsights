export interface SessionRead {
	id: string;
	session_id: string | null;
	user_id: string | null;
	project_name: string | null;
	start_time: string;
	end_time: string | null;
	model: string | null;
	total_tokens: number;
	status: 'pending' | 'analyzed' | 'failed';
	tool_call_count: number;
	insight_count: number;
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
	status: string;
	tool_calls: ToolCallRead[];
	insights: InsightRead[];
}

export interface StatsResponse {
	total_sessions: number;
	analyzed_sessions: number;
	total_insights: number;
	top_tools: Record<string, number>;
	insight_counts: Record<string, number>;
}
