const messages = document.querySelector('#messages');
const emptyState = messages.querySelector('.hint').cloneNode(true);
const form = document.querySelector('#chat-form');
const input = document.querySelector('#message');
const fileInput = document.querySelector('#file');
const fileStatus = document.querySelector('#file-status');
const fileWarning = document.querySelector('#file-warning');
const removeButton = document.querySelector('#remove');
const downloadLink = document.querySelector('#download');
const editedDownload = document.querySelector('#edited-download');
const generatedDownload = document.querySelector('#generated-download');
const sendButton = document.querySelector('#send');
const errorBox = document.querySelector('#error');
const themeToggle = document.querySelector('#theme-toggle');
const app = document.querySelector('[data-app]');
let busy = false;

function setTheme(theme) {
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

function showError(message) { errorBox.textContent = message || ''; errorBox.hidden = !message; }
function showFileWarning(message) { fileWarning.textContent = message || ''; fileWarning.hidden = !message; }
function showGeneratedFile(filename) {
  generatedDownload.hidden = !filename;
  generatedDownload.textContent = filename ? `Download generated file: ${filename}` : 'Download generated file';
}
function setBusy(value) {
  busy = value;
  sendButton.disabled = value;
  fileInput.disabled = value;
  removeButton.disabled = value;
  input.disabled = value;
}
function addMessage(role, text) {
  const hint = messages.querySelector('.hint');
  if (hint) hint.remove();
  const bubble = document.createElement('div');
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  messages.append(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}
function resetMessages() { messages.replaceChildren(emptyState.cloneNode(true)); }
function addSources(bubble, sources) {
  if (!sources?.length) return;
  const list = document.createElement('div');
  list.className = 'sources';
  const label = document.createElement('strong');
  label.textContent = 'Web sources:';
  list.append(label);
  for (const source of sources) {
    let url;
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
async function request(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Request failed');
    error.status = response.status;
    throw error;
  }
  return data;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !input.value.trim()) return;
  showError('');
  const question = input.value.trim();
  input.value = '';
  addMessage('user', question);
  const pending = addMessage('assistant', 'Thinking…');
  setBusy(true);
  try {
    const result = await request('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: question }),
    });
    pending.textContent = result.display_answer ?? result.answer;
    addSources(pending, result.sources);
    showGeneratedFile(result.generated_filename);
    editedDownload.hidden = !result.edited_filename;
  } catch (error) {
    pending.remove();
    showError(error.message);
  } finally { setBusy(false); input.focus(); }
});

fileInput.addEventListener('change', async () => {
  const file = fileInput.files[0];
  if (!file) return;
  showError('');
  showFileWarning('');
  const data = new FormData();
  data.append('file', file);
  setBusy(true);
  try {
    const result = await request('/api/document', { method: 'POST', body: data });
    fileStatus.textContent = `${result.filename}: ${result.status}`;
    removeButton.hidden = false;
    downloadLink.hidden = false;
    editedDownload.hidden = true;
    resetMessages();
  } catch (error) {
    showFileWarning(error.message);
  }
  finally { fileInput.value = ''; setBusy(false); }
});

removeButton.addEventListener('click', async () => {
  if (busy) return;
  showError(''); showFileWarning(''); setBusy(true);
  try {
    await request('/api/document', { method: 'DELETE' });
    fileStatus.textContent = 'No file selected. You can still chat normally.';
    removeButton.hidden = true;
    downloadLink.hidden = true;
    editedDownload.hidden = true;
    resetMessages();
  } catch (error) { showError(error.message); }
  finally { setBusy(false); }
});

(async () => {
  try {
    const state = await request('/api/state');
    if (state.filename) { fileStatus.textContent = `${state.filename}: ${state.status}`; removeButton.hidden = false; downloadLink.hidden = false; }
    showGeneratedFile(state.generated_filename);
    editedDownload.hidden = !state.edited_filename;
    for (const message of state.messages) addSources(addMessage(message.role, message.content), message.sources);
  } catch (error) { showError(error.message); }
})();
