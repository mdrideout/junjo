// @ts-check
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, passthroughImageService } from "astro/config";
import starlight from "@astrojs/starlight";
import tailwindcss from "@tailwindcss/vite";

const hasAgentGuides = existsSync(
  fileURLToPath(
    new URL("./src/content/docs/generated/docs/python/agents/index.md", import.meta.url),
  ),
);

// https://astro.build/config
export default defineConfig({
  site: "https://junjo.ai",
  integrations: [
    starlight({
      title: "Junjo AI",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/mdrideout/junjo",
        },
        {
          icon: "twitter",
          label: "Twitter",
          href: "https://twitter.com/junjo_ai",
        },
      ],
      customCss: ["./src/styles/global.css"],
      sidebar: [
        {
          label: "Documentation",
          items: [{ label: "Documentation Home", slug: "docs" }],
        },
        {
          label: "Python SDK",
          items: [
            { label: "Overview", slug: "docs/python" },
            { label: "Getting Started", slug: "docs/python/get-started" },
            { label: "Tutorial", slug: "docs/python/tutorial" },
            { label: "Core Concepts", slug: "docs/python/concepts" },
            ...(hasAgentGuides
              ? [
                  {
                    label: "Agents",
                    items: [
                      { label: "Agents", slug: "docs/python/agents" },
                      { label: "Testing", slug: "docs/python/agents/testing" },
                      { label: "Composition", slug: "docs/python/agents/composition" },
                    ],
                  },
                ]
              : []),
            {
              label: "Workflows",
              items: [
                { label: "State Management", slug: "docs/python/workflows/state" },
                { label: "Concurrency", slug: "docs/python/workflows/concurrency" },
                { label: "Subflows", slug: "docs/python/workflows/subflows" },
                { label: "Visualization", slug: "docs/python/workflows/visualization" },
              ],
            },
            { label: "Hooks", slug: "docs/python/hooks" },
            {
              label: "Eval-Driven Development",
              slug: "docs/python/testing/eval-driven-development",
            },
            { label: "API Reference", slug: "docs/python/api" },
          ],
        },
        {
          label: "Observability",
          items: [{ label: "OpenTelemetry", slug: "docs/observability/opentelemetry" }],
        },
        {
          label: "Junjo AI Studio",
          items: [
            { label: "Overview", slug: "docs/studio/overview" },
            { label: "Deployment", slug: "docs/studio/deployment" },
            { label: "Docker Reference", slug: "docs/studio/docker-reference" },
          ],
        },
      ],
    }),
  ],
  image: {
    service: passthroughImageService(),
  },

  vite: {
    plugins: [tailwindcss()],
  },
});
