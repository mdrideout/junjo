// vite-plugin-custom-startup-message.js

import { green, bold } from 'colorette' // For colorful output

export default function viteJunjoPlugin(options = {}) {
  return {
    name: 'vite-junjo-plugin',
    configureServer(server: any) {
      server.printUrls = () => {
        // Overrides the printUrls to prevent duplicated prints.
        // Optional: Clear the console for a cleaner look
        console.clear()

        // Your custom message here!  Customize as you like.
        console.log(
          bold(
            green(`
  🎏 Junjo Server UI is running 🎏 

  Local:    ${server.config.server.https ? 'https' : 'http'}://localhost:${server.config.server.port}
  Network:  ${server.resolvedUrls.network[0]}

  ----------------------------------
        `),
          ),
        )
      }
    },
  }
}
