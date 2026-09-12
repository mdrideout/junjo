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
const hasModelDriversGuide = existsSync(
  fileURLToPath(
    new URL("./src/content/docs/generated/docs/python/agents/model-drivers.md", import.meta.url),
  ),
);
const hasOpenAIAgentsGuide = existsSync(
  fileURLToPath(
    new URL(
      "./src/content/docs/generated/docs/python/integrations/openai-agents.md",
      import.meta.url,
    ),
  ),
);

// https://astro.build/config
export default defineConfig({
  site: "https://junjo.ai",
  integrations: [
    starlight({
      title: "Junjo AI",
      head: [
        { tag: "meta", attrs: { property: "og:image", content: "https://junjo.ai/social/junjo-og-image-1.jpg" } },
        { tag: "meta", attrs: { property: "og:image:alt", content: "Junjo: recursive self improvement for your AI application. Python SDK + AI Studio." } },
        { tag: "meta", attrs: { name: "twitter:card", content: "summary_large_image" } },
        { tag: "meta", attrs: { name: "twitter:image", content: "https://junjo.ai/social/junjo-og-image-1.jpg" } },
      ],
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
          label: "Start here",
          items: [
            { label: "Junjo in your stack", slug: "docs" },
            { label: "Recursive self improvement", slug: "docs/recursive-self-improvement" },
            { label: "Datasets and evaluation runs", slug: "docs/python/evaluation" },
          ],
        },
        {
          label: "Python SDK",
          items: [
            { label: "Overview", slug: "docs/python" },
            { label: "Getting Started", slug: "docs/python/get-started" },
            { label: "Tutorial", slug: "docs/python/tutorial" },
            { label: "Structured Workflows", slug: "docs/python/concepts" },
            ...(hasAgentGuides
              ? [
                  {
                    label: "Agents",
                    items: [
                      { label: "Specialist Agents", slug: "docs/python/agents" },
                      { label: "Testing", slug: "docs/python/agents/testing" },
                      { label: "Composition", slug: "docs/python/agents/composition" },
                      ...(hasModelDriversGuide
                        ? [{ label: "Model Drivers", slug: "docs/python/agents/model-drivers" }]
                        : []),
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
            ...(hasOpenAIAgentsGuide
              ? [
                  {
                    label: "Integrations",
                    items: [
                      {
                        label: "OpenAI Agents SDK",
                        slug: "docs/python/integrations/openai-agents",
                      },
                    ],
                  },
                ]
              : []),
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
