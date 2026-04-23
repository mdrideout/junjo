// vite-plugin-custom-startup-message.js

import { green, bold } from 'colorette' // For colorful output

export default function viteJunjoPlugin() {
  return {
    name: 'vite-junjo-plugin',
    configureServer(server: any) {
      server.printUrls = () => {
        // Overrides the printUrls to prevent duplicated prints.
        // Optional: Clear the console for a cleaner look
        console.clear()

        const scheme = server.config.server.https ? 'https' : 'http'
        const containerPort = server.config.server.port ?? 5151
        const hostPort = 26151
        const hostUrl = `${scheme}://localhost:${hostPort}`
        const containerUrl = `${scheme}://0.0.0.0:${containerPort}`
        const networkUrl = server.resolvedUrls.network?.[0] ?? 'unavailable'

        // Your custom message here!  Customize as you like.
        console.log(
          bold(
            green(`
  🎏 Junjo AI Studio UI is running (Development) 🎏 

  Host:      ${hostUrl}
  Container: ${containerUrl}
  Network:   ${networkUrl}

  ----------------------------------
        `),
          ),
        )
      }
    },
  }
}
