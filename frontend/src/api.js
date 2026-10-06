const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request to ${path} failed (${res.status})`);
  }
  return res.json();
}

export function fetchQueue() {
  return request('/conversations');
}

export function fetchConversation(id) {
  return request(`/conversations/${id}`);
}

export function resolveConversation(id) {
  return request(`/conversations/${id}/resolve`, { method: 'POST' });
}
