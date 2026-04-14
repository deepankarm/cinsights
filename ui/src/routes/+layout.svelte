<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();

</script>

<div class="app">
	<header>
		<nav>
			<a href="/" class="logo">cinsights</a>
			<div class="nav-links">
				<a href="/" class="nav-link">Dashboard</a>
				<a href="/projects" class="nav-link">Projects</a>
				<a href="/developers" class="nav-link">Developers</a>
				<a href="/sessions" class="nav-link">Sessions</a>
				<a href="/doctor" class="nav-link">Doctor</a>
			</div>
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
		font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
		background: #f6f4f0;
		color: #232326;
		line-height: 1.55;
		-webkit-font-smoothing: antialiased;
		transition: background 0.3s ease;
	}

	:global(a) { color: inherit; }

	.app {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		background: #f6f4f0;
	}

	header {
		padding: 0 40px;
		height: 56px;
		display: flex;
		align-items: center;
		position: sticky;
		top: 0;
		z-index: 100;
		background: rgba(246,244,240,0.88);
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
	}

	nav {
		display: flex;
		align-items: center;
		width: 100%;
		max-width: 1200px;
		margin: 0 auto;
	}

	.logo {
		font-size: 17px;
		font-weight: 800;
		text-decoration: none;
		color: #232326;
		letter-spacing: -0.5px;
	}

	.nav-links {
		margin-left: auto;
		display: flex;
		gap: 2px;
	}

	.nav-link {
		text-decoration: none;
		font-size: 13px;
		font-weight: 500;
		color: #70707a;
		padding: 6px 14px;
		border-radius: 8px;
		transition: all 0.15s;
	}

	.nav-link:hover {
		color: #232326;
		background: rgba(0,0,0,0.04);
	}

	main {
		flex: 1;
		max-width: 1200px;
		width: 100%;
		margin: 0 auto;
		padding: 40px 40px 80px;
	}

	@media (max-width: 768px) {
		header { padding: 0 20px; }
		main { padding: 24px 20px 60px; }
	}
</style>
