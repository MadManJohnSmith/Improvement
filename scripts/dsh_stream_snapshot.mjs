#!/usr/bin/env node
/** One-shot authoritative snapshot of DSH session/follow + session/control. */

const chunks = []
for await (const chunk of process.stdin) chunks.push(chunk)
let input
try {
  input = JSON.parse(Buffer.concat(chunks).toString('utf8'))
} catch (error) {
  process.stderr.write(`invalid input: ${String(error)}\n`)
  process.exit(2)
}

const { baseUrl, cookie, sessionId, timeoutMs = 10000 } = input ?? {}
if (typeof baseUrl !== 'string' || typeof cookie !== 'string' ||
    typeof sessionId !== 'string' || !Number.isFinite(timeoutMs)) {
  process.stderr.write('baseUrl, cookie, sessionId and timeoutMs are required\n')
  process.exit(2)
}

const url = new URL('/api/remote.mux', baseUrl)
url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
const socket = new WebSocket(url, { headers: { Cookie: cookie } })
const followId = `follow-${crypto.randomUUID()}`
const controlId = `control-${crypto.randomUUID()}`
let follow
let control
let settled = false

const finish = (error) => {
  if (settled) return
  settled = true
  clearTimeout(timer)
  try {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'cancel', streamId: followId }))
      socket.send(JSON.stringify({ type: 'cancel', streamId: controlId }))
      socket.close(1000, 'snapshot complete')
    }
  } catch {}
  if (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`)
    process.exitCode = 1
    return
  }
  process.stdout.write(JSON.stringify({ follow, control }) + '\n')
}

const timer = setTimeout(() => finish(new Error('DSH Remote stream snapshot timed out')), timeoutMs)

socket.addEventListener('open', () => {
  socket.send(JSON.stringify({
    type: 'open', streamId: followId, endpoint: 'session/follow',
    payload: { args: { request: {
      address: { kind: 'session', sessionId }, maxMessages: 200
    } } }
  }))
  socket.send(JSON.stringify({
    type: 'open', streamId: controlId, endpoint: 'session/control',
    payload: { args: {} }
  }))
})

socket.addEventListener('message', async (message) => {
  try {
    let text
    if (typeof message.data === 'string') text = message.data
    else if (message.data instanceof Blob) text = await message.data.text()
    else text = Buffer.from(message.data).toString('utf8')
    const frame = JSON.parse(text)
    if (frame.type === 'error') {
      finish(new Error(`${frame.error?.code ?? 'stream/error'}: ${frame.error?.message ?? 'unknown error'}`))
      return
    }
    if (frame.type !== 'item') return
    if (frame.streamId === followId && frame.value?.type === 'snapshot') follow = frame.value
    if (frame.streamId === controlId && frame.value?.type === 'baseline') control = frame.value.value
    if (follow !== undefined && control !== undefined) finish()
  } catch (error) {
    finish(error)
  }
})
socket.addEventListener('error', () => finish(new Error('DSH Remote stream WebSocket failed')))
socket.addEventListener('close', () => {
  if (!settled) finish(new Error('DSH Remote stream WebSocket closed before both baselines'))
})
