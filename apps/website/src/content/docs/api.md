---
title: Python API Compatibility Redirect
description: Compatibility route for links from the former Sphinx API reference.
sidebar:
  hidden: true
pagefind: false
---

Existing Sphinx API links are being mapped to the generated Python reference.
If this page does not redirect automatically, open the [Python API
reference](/docs/python/api/).

<script>
  async function redirectLegacyApiFragment() {
    const fragment = decodeURIComponent(window.location.hash.slice(1));
    if (!fragment) return;
    const response = await fetch("/docs-manifests/generated/python/legacy-api-map.json");
    if (!response.ok) return;
    const payload = await response.json();
    const target = payload.symbols?.[fragment];
    if (target) window.location.replace(target);
  }
  redirectLegacyApiFragment();
</script>
