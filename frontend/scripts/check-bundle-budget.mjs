import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const entryMatch = html.match(/<script[^>]+src="([^"]+\.js)"/)

if (!entryMatch) {
  throw new Error('Cannot find the production entry script in dist/index.html')
}

const entryPath = new URL(`../dist/${entryMatch[1].replace(/^\//, '')}`, import.meta.url)
const entry = readFileSync(entryPath)
const rawKb = entry.byteLength / 1024
const gzipKb = gzipSync(entry).byteLength / 1024
const rawLimitKb = 700
const gzipLimitKb = 220

console.log(`Production entry: ${rawKb.toFixed(2)} kB raw, ${gzipKb.toFixed(2)} kB gzip`)

if (rawKb > rawLimitKb || gzipKb > gzipLimitKb) {
  throw new Error(
    `Production entry exceeds budget (${rawLimitKb} kB raw / ${gzipLimitKb} kB gzip)`,
  )
}
