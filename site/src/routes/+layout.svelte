<script>
  import { base } from "$app/paths";
  import "prismjs/themes/prism-tomorrow.css";
</script>

<nav class="border-b border-slate-800 px-6 py-4 flex items-center gap-6">
  <a href={base + "/"} class="text-cyan-400 font-bold text-lg no-underline">
    ⚡ ADK Patterns
  </a>
  <div class="flex gap-4 text-sm">
    <a href={base + "/patterns/"} class="text-slate-400 hover:text-cyan-300 no-underline">
      Patterns
    </a>
    <a href="https://github.com/rmax-ai/adk-agentic-patterns" class="text-slate-500 hover:text-cyan-300 no-underline" target="_blank">
      GitHub ↗
    </a>
  </div>
</nav>

<main class="max-w-4xl mx-auto px-6 py-8">
  <slot />
</main>

<footer class="border-t border-slate-800 px-6 py-4 text-center text-slate-600 text-xs">
  ADK Agentic Design Patterns · MIT License · Built with Google ADK 2.3.0
</footer>

<style>
  :global(body) {
    font-family: "JetBrains Mono", ui-monospace, monospace;
  }
  :global(a) {
    color: #22d3ee;
  }
  :global(a:hover) {
    color: #67e8f9;
  }
  :global(code) {
    background: #1e293b;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    font-size: 0.875em;
  }
  :global(pre) {
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 0.5rem;
    padding: 1rem;
    overflow-x: auto;
  }
  :global(pre code) {
    background: none;
    padding: 0;
  }
  :global(h1) {
    font-size: 1.75rem;
    font-weight: 700;
    color: #e2e8f0;
    margin-top: 2rem;
    margin-bottom: 0.5rem;
  }
  :global(h2) {
    font-size: 1.25rem;
    font-weight: 600;
    color: #cbd5e1;
    margin-top: 1.75rem;
    margin-bottom: 0.5rem;
  }
  :global(h3) {
    font-size: 1rem;
    font-weight: 600;
    color: #94a3b8;
    margin-top: 1.25rem;
    margin-bottom: 0.25rem;
  }
  :global(p) {
    line-height: 1.7;
    margin-bottom: 0.75rem;
  }
  :global(ul), :global(ol) {
    padding-left: 1.5rem;
    margin-bottom: 0.75rem;
  }
  :global(li) {
    line-height: 1.6;
  }
  :global(blockquote) {
    border-left: 3px solid #334155;
    padding-left: 1rem;
    margin: 1rem 0;
    color: #94a3b8;
  }
  :global(hr) {
    border: none;
    border-top: 1px solid #334155;
    margin: 2rem 0;
  }
  :global(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
  }
  :global(th) {
    text-align: left;
    padding: 0.5rem 0.75rem;
    border-bottom: 2px solid #334155;
    color: #94a3b8;
    font-size: 0.75rem;
    text-transform: uppercase;
  }
  :global(td) {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #1e293b;
  }
</style>
