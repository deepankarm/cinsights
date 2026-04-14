<script lang="ts">
	import { toPng } from 'html-to-image';
	import { jsPDF } from 'jspdf';

	let { target, filename = 'report' }: { target: HTMLElement | null; filename?: string } = $props();
	let exporting = $state(false);

	async function exportPDF() {
		if (!target || exporting) return;
		exporting = true;

		try {
			// Capture the entire target element as a high-res PNG
			const dataUrl = await toPng(target, {
				backgroundColor: '#f6f4f0',
				pixelRatio: 2,
				filter: (node: HTMLElement) => {
					// Exclude the export button itself from the capture
					return !node?.classList?.contains('export-btn-wrapper');
				},
			});

			const img = new Image();
			img.src = dataUrl;
			await new Promise((resolve) => { img.onload = resolve; });

			const pxWidth = img.naturalWidth;
			const pxHeight = img.naturalHeight;

			// A4 dimensions in mm
			const pageW = 210;
			const pageH = 297;
			const margin = 10;
			const contentW = pageW - margin * 2;

			// Scale image to fit page width
			const scale = contentW / pxWidth;
			const imgHeightMm = pxHeight * scale;
			const contentH = pageH - margin * 2;

			const pdf = new jsPDF('p', 'mm', 'a4');
			let yOffset = 0;

			// Paginate: slice the image into page-sized chunks
			while (yOffset < imgHeightMm) {
				if (yOffset > 0) pdf.addPage();

				// Calculate source crop in pixels
				const srcY = yOffset / scale;
				const srcH = Math.min(contentH / scale, pxHeight - srcY);
				const destH = srcH * scale;

				// Use a canvas to crop the section
				const canvas = document.createElement('canvas');
				canvas.width = pxWidth;
				canvas.height = Math.ceil(srcH);
				const ctx = canvas.getContext('2d')!;
				ctx.drawImage(img, 0, srcY, pxWidth, srcH, 0, 0, pxWidth, srcH);

				const sectionData = canvas.toDataURL('image/png');
				pdf.addImage(sectionData, 'PNG', margin, margin, contentW, destH);

				yOffset += contentH;
			}

			pdf.save(`${filename}.pdf`);
		} catch (e) {
			console.error('PDF export failed:', e);
			alert('Export failed. Check the console for details.');
		} finally {
			exporting = false;
		}
	}
</script>

<div class="export-btn-wrapper">
	<button class="export-btn" onclick={exportPDF} disabled={exporting || !target}>
		{#if exporting}
			<span class="spinner"></span> Exporting...
		{:else}
			<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
				<path d="M8 1v9M8 10L5 7M8 10l3-3M2 12v1.5A1.5 1.5 0 003.5 15h9a1.5 1.5 0 001.5-1.5V12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
			</svg>
			Export PDF
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
