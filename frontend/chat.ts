type Source = { title: string; url: string };
type ChatMessage = { role: string; content: string; sources?: Source[] };
type User = { id: number; name: string };
type ChatState = {
  user_id: number | null;
  filename: string;
  status: string;
  generated_filename: string;
  edited_filename: string;
};
type ChatReply = { answer: string; display_answer?: string; sources: Source[]; generated_filename: string; edited_filename: string };
type UploadResult = { filename: string; status: string };

function element<T extends Element>(selector: string): T {
  const found = document.querySelector<T>(selector);
  if (!found) throw new Error(`Missing element: ${selector}`);
  return found;
}

const messages = element<HTMLElement>('#messages');
const emptyState = element<HTMLElement>('#messages .hint').cloneNode(true);
const form = element<HTMLFormElement>('#chat-form');
const input = element<HTMLInputElement>('#message');
const fileInput = element<HTMLInputElement>('#file');
const attachButton = element<HTMLButtonElement>('#attach');
const fileStatus = element<HTMLElement>('#file-status');
const fileWarning = element<HTMLElement>('#file-warning');
const removeButton = element<HTMLButtonElement>('#remove');
const downloadLink = element<HTMLAnchorElement>('#download');
const editedDownload = element<HTMLAnchorElement>('#edited-download');
const generatedDownload = element<HTMLAnchorElement>('#generated-download');
const sendButton = element<HTMLButtonElement>('#send');
const errorBox = element<HTMLElement>('#error');
const themeToggle = element<HTMLButtonElement>('#theme-toggle');
const app = element<HTMLElement>('[data-app]');
const userSelect = element<HTMLSelectElement>('#user-select');
const userForm = element<HTMLFormElement>('#user-form');
const userName = element<HTMLInputElement>('#user-name');
const userSubmit = element<HTMLButtonElement>('#user-form button');
let busy = false;
let activeUser: number | null = null;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Request failed';
}

function setTheme(theme: 'light' | 'dark'): void {
  app.dataset.theme = theme;
  themeToggle.textContent = theme === 'light' ? 'Dark mode' : 'Light mode';
  themeToggle.setAttribute('aria-label', `Switch to ${theme === 'light' ? 'dark' : 'light'} theme`);
}
try { setTheme(localStorage.getItem('chat-theme') === 'dark' ? 'dark' : 'light'); }
catch { setTheme('light'); }
themeToggle.addEventListener('click', () => {
  const theme = app.dataset.theme === 'light' ? 'dark' : 'light';
  setTheme(theme);
  try { localStorage.setItem('chat-theme', theme); } catch {}
});

function showError(message: string): void { errorBox.textContent = message || ''; errorBox.hidden = !message; }
function showFileWarning(message: string): void { fileWarning.textContent = message || ''; fileWarning.hidden = !message; }
function showGeneratedFile(filename: string): void {
  generatedDownload.hidden = !filename;
  generatedDownload.textContent = filename ? `Download generated file: ${filename}` : 'Download generated file';
}
function setBusy(value: boolean): void {
  busy = value;
  sendButton.disabled = value;
  fileInput.disabled = value || !activeUser;
  attachButton.disabled = value || !activeUser;
  removeButton.disabled = value;
  input.disabled = value || !activeUser;
  userSelect.disabled = value;
  userName.disabled = value;
  userSubmit.disabled = value;
}
function addMessage(role: string, text: string): HTMLDivElement {
  const hint = messages.querySelector('.hint');
  if (hint) hint.remove();
  const bubble = document.createElement('div');
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  messages.append(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}
function resetMessages(): void { messages.replaceChildren(emptyState.cloneNode(true)); }
function addSources(bubble: HTMLElement, sources?: Source[]): void {
  if (!sources?.length) return;
  const list = document.createElement('div');
  list.className = 'sources';
  const label = document.createElement('strong');
  label.textContent = 'Web sources:';
  list.append(label);
  for (const source of sources) {
    let url: URL;
    try { url = new URL(source.url); } catch { continue; }
    if (!['https:', 'http:'].includes(url.protocol)) continue;
    const link = document.createElement('a');
    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = source.title || url.href;
    list.append(link);
  }
  bubble.append(list);
}
function renderMessages(items: ChatMessage[]): void {
  resetMessages();
  for (const message of items) addSources(addMessage(message.role, message.content), message.sources);
}
function renderState(state: ChatState): void {
  fileStatus.textContent = state.filename ? `${state.filename}: ${state.status}` : '';
  fileStatus.hidden = !state.filename;
  removeButton.hidden = !state.filename;
  downloadLink.hidden = !state.filename;
  editedDownload.hidden = !state.edited_filename;
  showGeneratedFile(state.generated_filename);
}
async function loadUsers(selected: number | null): Promise<void> {
  const users = await request<User[]>('/api/users');
  userSelect.replaceChildren(new Option('Select a user', ''));
  for (const user of users) userSelect.add(new Option(user.name, String(user.id)));
  userSelect.value = selected ? String(selected) : '';
}
async function selectUser(id: number | string): Promise<void> {
  if (!id) return;
  setBusy(true);
  try {
    await request(`/api/users/${id}/select`, { method: 'POST' });
    activeUser = Number(id);
    userSelect.value = String(id);
    const [history, state] = await Promise.all([
      request<ChatMessage[]>(`/api/users/${id}/messages`), request<ChatState>('/api/state'),
    ]);
    renderMessages(history);
    renderState(state);
    showError('');
  } catch (error) { userSelect.value = String(activeUser || ''); showError(errorMessage(error)); }
  finally { setBusy(false); }
}
userForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  setBusy(true);
  try {
    const user = await request<User>('/api/users', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: userName.value.trim() }),
    });
    userName.value = '';
    await loadUsers(user.id);
    await selectUser(user.id);
  } catch (error) { showError(errorMessage(error)); }
  finally { setBusy(false); }
});
userSelect.addEventListener('change', () => {
  if (!userSelect.value) { userSelect.value = String(activeUser || ''); return; }
  selectUser(userSelect.value);
});
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  const data: unknown = await response.json();
  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail;
    const error = new Error(typeof detail === 'string' ? detail : 'Request failed');
    (error as Error & { status: number }).status = response.status;
    throw error;
  }
  return data as T;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !activeUser || !input.value.trim()) return;
  showError('');
  const question = input.value.trim();
  input.value = '';
  addMessage('user', question);
  const pending = addMessage('assistant', 'Thinking…');
  setBusy(true);
  try {
    const result = await request<ChatReply>('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: question }),
    });
    pending.textContent = result.display_answer ?? result.answer;
    addSources(pending, result.sources);
    showGeneratedFile(result.generated_filename);
    editedDownload.hidden = !result.edited_filename;
  } catch (error) {
    pending.remove();
    showError(errorMessage(error));
  } finally { setBusy(false); input.focus(); }
});

attachButton.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async () => {
  const file = fileInput.files?.[0];
  if (!file || !activeUser) return;
  showError('');
  showFileWarning('');
  const data = new FormData();
  data.append('file', file);
  setBusy(true);
  try {
    const result = await request<UploadResult>('/api/document', { method: 'POST', body: data });
    fileStatus.textContent = `${result.filename}: ${result.status}`;
    fileStatus.hidden = false;
    removeButton.hidden = false;
    downloadLink.hidden = false;
    editedDownload.hidden = true;
  } catch (error) {
    showFileWarning(errorMessage(error));
  }
  finally { fileInput.value = ''; setBusy(false); }
});

removeButton.addEventListener('click', async () => {
  if (busy) return;
  showError(''); showFileWarning(''); setBusy(true);
  try {
    await request('/api/document', { method: 'DELETE' });
    fileStatus.textContent = '';
    fileStatus.hidden = true;
    removeButton.hidden = true;
    downloadLink.hidden = true;
    editedDownload.hidden = true;
  } catch (error) { showError(errorMessage(error)); }
  finally { setBusy(false); }
});

setBusy(false);
(async () => {
  try {
    const state = await request<ChatState>('/api/state');
    activeUser = state.user_id;
    renderState(state);
    await loadUsers(activeUser);
    if (activeUser) await selectUser(activeUser);
    else setBusy(false);
  } catch (error) { showError(errorMessage(error)); }
})();
