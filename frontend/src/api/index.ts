export interface ApiUser {
  id: number
  name: string
  template_count: number
  hands: { L?: number; R?: number }
  created_at: string
}

export interface EnrollResult {
  user_id: number
  captured: number
  quality: number
  hand_side: string
}

export interface VerifyResult {
  matched: boolean
  user: { id: number; name: string } | null
  distance: number
  threshold: number
  confidence: number
  hand_side: string
}

export interface PreviewStatus {
  ready: boolean
  status: string
  reason: string
  quality: number
  solidity: number | null
}

export interface LogRow {
  id: number
  user_id: number | null
  user_name: string | null
  matched: number
  distance: number
  threshold: number
  created_at: string
}

export interface CameraInfo {
  index: number
  available: boolean
  width: number
  height: number
}

export interface CamerasResp {
  cameras: CameraInfo[]
  current_index: number | null
}

export interface HardwareStatus {
  enabled: boolean
  connected: boolean
  port: string | null
  baudrate: number | null
  error: string | null
}

export interface HealthResp {
  db: boolean
  camera: boolean
  hardware: HardwareStatus
}

interface ApiEnvelope<T> {
  ok: boolean
  data: T
  error: string | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  const body = (await res.json()) as ApiEnvelope<T>
  if (!body.ok) {
    throw new Error(body.error || `HTTP ${res.status}`)
  }
  return body.data
}

export const api = {
  enroll(name: string, samples = 5) {
    return request<EnrollResult>('/api/enroll', {
      method: 'POST',
      body: JSON.stringify({ name, samples }),
    })
  },
  users() {
    return request<ApiUser[]>('/api/users')
  },
  deleteUser(id: number) {
    return request<{ deleted: number }>(`/api/users/${id}`, { method: 'DELETE' })
  },
  verify() {
    return request<VerifyResult>('/api/verify', { method: 'POST', body: '{}' })
  },
  previewStatus() {
    return request<PreviewStatus>('/api/preview_status')
  },
  logs(limit = 50) {
    return request<LogRow[]>(`/api/logs?limit=${limit}`)
  },
  health() {
    return request<HealthResp>('/api/health')
  },
  cameras() {
    return request<CamerasResp>('/api/cameras')
  },
  selectCamera(index: number) {
    return request<{ index: number }>('/api/camera/select', {
      method: 'POST',
      body: JSON.stringify({ index }),
    })
  },
}
