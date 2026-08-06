<script lang="ts">
  import LegacyResumePage from '../generate/+page.svelte';

  let { data } = $props();
</script>

<LegacyResumePage {data} />
