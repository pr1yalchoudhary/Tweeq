import { test, expect } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs/promises'

const artifacts = path.resolve('..', 'test-results', 'stage-one', 'artifacts')
const usage = { mode: 'public', remaining: 2, global_remaining: 10, visitor_remaining: 2,
  message: 'Each voice setup, speech detection and generation uses one allowance. Failed attempts count too.' }
function wav() {
  const seconds = 12, rate = 16000, bytes = seconds * rate * 2
  const out = Buffer.alloc(44 + bytes)
  out.write('RIFF', 0); out.writeUInt32LE(36 + bytes, 4); out.write('WAVEfmt ', 8); out.writeUInt32LE(16, 16)
  out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22); out.writeUInt32LE(rate, 24); out.writeUInt32LE(rate * 2, 28)
  out.writeUInt16LE(2, 32); out.writeUInt16LE(16, 34); out.write('data', 36); out.writeUInt32LE(bytes, 40)
  for (let i = 0; i < seconds * rate; i++) out.writeInt16LE(Math.round(Math.sin(i * 2 * Math.PI * 220 / rate) * 5000), 44 + i * 2)
  return out
}

async function isolate(page, options = {}) {
  const apiCalls = [], blocked = [], errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.context().route('**/*', async route => {
    const request = route.request(), url = new URL(request.url())
    if (url.pathname.startsWith('/api/')) {
      apiCalls.push({ path: url.pathname, method: request.method() })
      if (url.pathname === '/api/public/session') return route.fulfill({ json: { ...(options.usage || usage), session_token: 'local-mock-visitor-token' } })
      if (url.pathname === '/api/public/usage') return route.fulfill({ json: options.usage || usage })
      if (url.pathname === '/api/upload') return options.uploadError
        ? route.fulfill({ status: 400, json: { detail: 'Local upload fixture was rejected. Choose another recording.' } })
        : route.fulfill({ json: { session_id: 'local-stage-one-fixture', name: 'local-recording.wav', duration: 12, original_duration: 12, revision: 0,
          voice_status: 'ready', voice_error: null, voice_prepared: false, reference_revision: 0,
          quality: { status: 'good', warnings: [] }, reference: { start: 0, end: 10 }, edit_count: 0, edit_history: [] } })
      if (url.pathname.startsWith('/api/audio/')) return route.fulfill({ contentType: 'audio/wav', body: wav() })
      blocked.push(url.pathname)
      return route.abort('blockedbyclient')
    }
    if (url.origin === 'http://127.0.0.1:5174') return route.continue()
    blocked.push(url.origin + url.pathname)
    return route.abort('blockedbyclient')
  })
  await page.goto('/')
  await expect(page.getByText(`${(options.usage || usage).remaining} free AI uses remaining`, { exact: true })).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  return { apiCalls, blocked, errors }
}

test('reference-size initial upload capture and exact panel geometry', async ({ page }) => {
  const state = await isolate(page)
  await expect(page.getByRole('heading', { name: 'Upload your recording' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open recording' })).toBeDisabled()
  await expect(page.getByRole('textbox', { name: 'Demo access code' })).toHaveCount(0)
  const shell = await page.locator('.upload-screen').boundingBox(), drop = await page.locator('.drop-zone').boundingBox()
  expect(shell.x).toBe(336); expect(shell.y).toBe(80)
  expect(Math.abs(drop.x - 366)).toBeLessThanOrEqual(1)
  expect(Math.abs(drop.y - 185)).toBeLessThanOrEqual(2)
  expect(state.apiCalls.every(call => call.path.startsWith('/api/public/'))).toBe(true)
  await fs.mkdir(artifacts, { recursive: true })
  await page.screenshot({ path: path.join(artifacts, 'stage-one-upload-1918x955.png') })
  await fs.writeFile(path.join(artifacts, 'initial-geometry.json'), JSON.stringify({ shell, drop, apiCalls: state.apiCalls }, null, 2))
  expect(state.blocked).toEqual([]); expect(state.errors).toEqual([])
})

test('file, consent, navigation and actual waveform loading preserve the upload workflow', async ({ page }) => {
  const state = await isolate(page)
  await page.getByLabel('Choose File', { exact: true }).setInputFiles({ name: 'local-recording.wav', mimeType: 'audio/wav', buffer: wav() })
  await expect(page.getByText('local-recording.wav', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open recording' })).toBeDisabled()
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Toggle navigation' }).click()
  await page.getByRole('button', { name: 'Toggle navigation' }).click()
  await expect(page.getByRole('checkbox')).toBeChecked()
  await expect(page.getByRole('button', { name: 'Open recording' })).toBeEnabled()
  await page.screenshot({ path: path.join(artifacts, 'stage-one-file-selected-1918x955.png') })
  await page.getByRole('button', { name: 'Open recording' }).click()
  await expect(page.getByRole('heading', { name: 'local-recording.wav' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Play current recording', exact: true })).toBeEnabled()
  await expect(page.locator('#step-edit')).toBeHidden()
  expect(state.apiCalls.filter(call => call.path === '/api/upload')).toHaveLength(1)
  expect(state.apiCalls.some(call => ['/api/preview', '/api/transcribe'].includes(call.path))).toBe(false)
  expect(state.blocked).toEqual([]); expect(state.errors).toEqual([])
})

test('backend upload errors keep the chosen file and consent available', async ({ page }) => {
  const state = await isolate(page, { uploadError: true })
  await page.getByLabel('Choose File', { exact: true }).setInputFiles({ name: 'local-recording.wav', mimeType: 'audio/wav', buffer: wav() })
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Open recording' }).click()
  await expect(page.getByRole('alert')).toContainText('Local upload fixture was rejected.')
  await expect(page.getByRole('checkbox')).toBeChecked()
  await expect(page.getByText('local-recording.wav', { exact: true })).toBeVisible()
  expect(state.blocked).toEqual([])
})

test('mobile layout has working navigation and no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const state = await isolate(page)
  await expect(page.getByRole('button', { name: 'Toggle navigation' })).toHaveAttribute('aria-expanded', 'false')
  await page.getByRole('button', { name: 'Toggle navigation' }).click()
  await expect(page.getByRole('navigation', { name: 'Workspace' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Toggle navigation' })).toHaveAttribute('aria-expanded', 'false')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: path.join(artifacts, 'stage-one-mobile-390x844.png') })
  await page.getByRole('button', { name: 'Open recording' }).scrollIntoViewIfNeeded()
  await expect(page.getByRole('checkbox')).toBeVisible()
  await page.screenshot({ path: path.join(artifacts, 'stage-one-mobile-details-390x844.png') })
  await page.getByRole('button', { name: 'Toggle navigation' }).click()
  await page.getByRole('link', { name: 'Recording', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Upload your recording' })).toBeInViewport()
  expect(state.blocked).toEqual([]); expect(state.errors).toEqual([])
})

test('narrow desktop keeps both upload columns usable', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const state = await isolate(page)
  const drop = await page.locator('.drop-zone').boundingBox(), details = await page.locator('.upload-details').boundingBox()
  expect(details.x).toBeGreaterThan(drop.x + drop.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Open recording' }).scrollIntoViewIfNeeded()
  await expect(page.getByRole('button', { name: 'Open recording' })).toBeVisible()
  await page.screenshot({ path: path.join(artifacts, 'stage-one-desktop-1280x800.png') })
  expect(state.blocked).toEqual([]); expect(state.errors).toEqual([])
})
