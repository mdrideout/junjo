// @ts-check
import { defineConfig, passthroughImageService } from "astro/config";
import starlight from "@astrojs/starlight";

import tailwindcss from "@tailwindcss/vite";

import "./src/styles/global.css";

// https://astro.build/config
export default defineConfig({
  integrations: [
    starlight({
      title: "Junjo AI",
      social: {
        github: "https://github.com/withastro/starlight",
      },
      sidebar: [
        {
          label: "Guides",
          items: [
            // Each item here is one entry in the navigation menu.
            { label: "Example Guide", slug: "guides/example" },
          ],
        },
        {
          label: "Reference",
          autogenerate: { directory: "reference" },
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
