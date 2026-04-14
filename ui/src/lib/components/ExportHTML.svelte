<script lang="ts">
	let { target, filename = 'report' }: { target: HTMLElement | null; filename?: string } = $props();
	let exporting = $state(false);

	async function exportHTML() {
		if (!target || exporting) return;
		exporting = true;

		try {
			// Expand all collapsible sections
			window.dispatchEvent(new CustomEvent('export-expand'));
			await new Promise(r => setTimeout(r, 300));

			// Collect all stylesheets
			const styles: string[] = [];
			for (const sheet of document.styleSheets) {
				try {
					const rules = Array.from(sheet.cssRules).map(r => r.cssText).join('\n');
					styles.push(rules);
				} catch {
					// Cross-origin sheets can't be read — skip
				}
			}

			// Clone target HTML
			const content = target.innerHTML;

			// Build self-contained HTML document
			const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${filename}</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
	font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
	background: #f6f4f0; color: #232326; line-height: 1.55;
	-webkit-font-smoothing: antialiased;
	padding: 40px; max-width: 1200px; margin: 0 auto;
}
a { color: inherit; }
${styles.join('\n')}
.export-btn-wrapper { display: none !important; }
</style>
</head>
<body>
${content}
</body>
</html>`;

			// Download as .html file
			const blob = new Blob([html], { type: 'text/html' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `${filename}.html`;
			a.click();
			URL.revokeObjectURL(url);
		} finally {
			window.dispatchEvent(new CustomEvent('export-collapse'));
			exporting = false;
		}
	}
</script>

<div class="export-btn-wrapper">
	<button class="export-btn" onclick={exportHTML} disabled={exporting || !target}>
		{#if exporting}
			<span class="spinner"></span> Preparing...
		{:else}
			<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
				<path d="M8 1v9M8 10L5 7M8 10l3-3M2 12v1.5A1.5 1.5 0 003.5 15h9a1.5 1.5 0 001.5-1.5V12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
			</svg>
			Export
		{/if}
	</button>
</div>

<style>
	.export-btn-wrapper { display: inline-flex; }
	.export-btn {
		display: inline-flex; align-items: center; gap: 6px;
		padding: 7px 16px;
		font-size: 13px; font-weight: 600;
		color: #475569; background: white;
		border: 1px solid #e2e8f0; border-radius: 8px;
		cursor: pointer; transition: all 0.15s;
		font-family: inherit;
	}
	.export-btn:hover:not(:disabled) {
		color: #232326;
		border-color: #cbd5e1;
		box-shadow: 0 1px 4px rgba(0,0,0,0.06);
	}
	.export-btn:disabled { opacity: 0.5; cursor: not-allowed; }

	.spinner {
		display: inline-block; width: 14px; height: 14px;
		border: 2px solid #e2e8f0; border-top-color: #475569;
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }
</style>
