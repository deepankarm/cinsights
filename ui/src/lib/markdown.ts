import { Marked } from 'marked';
import hljs from 'highlight.js';

const marked = new Marked({
	renderer: {
		code({ text, lang }: { text: string; lang?: string }) {
			const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
			const highlighted = hljs.highlight(text, { language }).value;
			return `<pre><code class="hljs language-${language}">${highlighted}</code></pre>`;
		}
	}
});

export function renderMarkdown(src: string): string {
	return marked.parse(src) as string;
}

export function linkifySessions(text: string, sessionIds: string[]): string {
	if (!sessionIds.length) return text;
	return text.replace(/Session (\d+)('s)?/gi, (match, num, _possessive) => {
		const idx = parseInt(num) - 1;
		if (idx >= 0 && idx < sessionIds.length) {
			return `[${match}](/sessions/${sessionIds[idx]})`;
		}
		return match;
	});
}

export function renderLinkedMarkdown(text: string, sessionIds: string[]): string {
	return renderMarkdown(linkifySessions(text, sessionIds));
}
