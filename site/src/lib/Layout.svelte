<script>
  export let title = "";
  export let description = "";
</script>

<svelte:head>
  <title>{title ? `${title} — ADK Patterns` : "ADK Agentic Patterns"}</title>
  <meta name="description" content={description || "Executable catalogue of 23 agentic design patterns using Google ADK"} />
</svelte:head>

<article>
  {#if title}
    <h1>{title}</h1>
  {/if}
  <slot />
</article>
