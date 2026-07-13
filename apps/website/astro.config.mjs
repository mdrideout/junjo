// @ts-check
import { defineConfig, passthroughImageService } from "astro/config";
import starlight from "@astrojs/starlight";
import tailwindcss from "@tailwindcss/vite";

// https://astro.build/config
export default defineConfig({
  site: "https://junjo.ai",
  redirects: {
    "/guides/example/": "/docs/guides/example/",
    "/reference/example/": "/docs/reference/example/",
  },
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
          slug: "docs",
        },
        {
          label: "Guides",
          autogenerate: { directory: "docs/guides" },
        },
        {
          label: "Reference",
          autogenerate: { directory: "docs/reference" },
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
