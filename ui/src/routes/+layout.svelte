<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<div class="app">
	<header>
		<nav>
			<a href="/" class="logo">cinsights</a>
			<span class="tagline">coding agent insights</span>
		</nav>
	</header>

	<main>
		{@render children()}
	</main>
</div>

<style>
	:global(*) {
		box-sizing: border-box;
		margin: 0;
		padding: 0;
	}

	:global(body) {
		font-family:
			'Inter',
			-apple-system,
			BlinkMacSystemFont,
			sans-serif;
		background: #f8fafc;
		color: #334155;
		line-height: 1.6;
	}

	.app {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	header {
		background: #0f172a;
		color: white;
		padding: 0 24px;
		height: 56px;
		display: flex;
		align-items: center;
	}

	nav {
		display: flex;
		align-items: baseline;
		gap: 12px;
	}

	.logo {
		font-size: 20px;
		font-weight: 700;
		color: white;
		text-decoration: none;
		letter-spacing: -0.5px;
	}

	.tagline {
		font-size: 13px;
		color: #94a3b8;
	}

	main {
		flex: 1;
		max-width: 1200px;
		width: 100%;
		margin: 0 auto;
		padding: 32px 24px;
	}
</style>
