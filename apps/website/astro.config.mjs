// @ts-check
import { defineConfig, passthroughImageService } from "astro/config";
import starlight from "@astrojs/starlight";
import tailwindcss from "@tailwindcss/vite";

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
          label: "Guides",
          items: [{ label: "Example Guide", slug: "guides/example" }],
        },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "reference" } }],
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
