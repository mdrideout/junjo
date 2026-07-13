// @ts-check
import { defineConfig, passthroughImageService } from "astro/config";
import starlight from "@astrojs/starlight";
import tailwindcss from "@tailwindcss/vite";

// https://astro.build/config
export default defineConfig({
  site: "https://junjo.ai",
  redirects: {
    "/guides/example/": "/docs/guides/getting-started/",
    "/reference/example/": "/docs/reference/platform/",
  },
  integrations: [
    starlight({
      title: "Junjo AI",
      disable404Route: true,
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
          link: "/docs/",
        },
        {
          label: "Guides",
          items: [{ autogenerate: { directory: "docs/guides" } }],
        },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "docs/reference" } }],
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
