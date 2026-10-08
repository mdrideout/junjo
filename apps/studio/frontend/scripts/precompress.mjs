// Compress each text file of a build once, so the server that sends the build
// never compresses per request. It serves `file.br` or `file.gz` to a browser
// that accepts it, and `file` otherwise.
//
// Usage: node scripts/precompress.mjs <build directory>

import { readdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { brotliCompressSync, constants, gzipSync } from 'node:zlib'

const TEXT_EXTENSIONS = new Set(['.css', '.html', '.js', '.json', '.svg', '.txt'])

async function* filesIn(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      yield* filesIn(entryPath)
    } else if (entry.isFile()) {
      yield entryPath
    }
  }
}

const buildDirectory = process.argv[2]
if (!buildDirectory) {
  console.error('Usage: node scripts/precompress.mjs <build directory>')
  process.exit(1)
}

let compressed = 0
for await (const file of filesIn(buildDirectory)) {
  if (!TEXT_EXTENSIONS.has(path.extname(file))) continue
  const content = await readFile(file)
  const brotli = brotliCompressSync(content, {
    params: {
      [constants.BROTLI_PARAM_QUALITY]: constants.BROTLI_MAX_QUALITY,
      [constants.BROTLI_PARAM_SIZE_HINT]: content.length,
    },
  })
  const gzip = gzipSync(content, { level: constants.Z_BEST_COMPRESSION })
  // A sibling that is not smaller is not written: the file is sent as it is.
  if (brotli.length < content.length) await writeFile(`${file}.br`, brotli)
  if (gzip.length < content.length) await writeFile(`${file}.gz`, gzip)
  compressed += 1
}
console.log(`Compressed ${compressed} files in ${buildDirectory}`)
