import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';

const sessions = new Map();
const users = [{ id: 1, name: 'Tester', email: 'tester@example.com' }, { id: 2, name: 'Other', email: 'other@example.com' }];
const conversations = [];
const histories = new Map();
const chatFiles = new Map();
const limits = new Map();
const uploadCounts = new Map();
const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64');
const imageNames = new Map();
const sourceSnapshots = new Map();
const previewPdf = readFileSync(new URL('./fixtures/preview.pdf', import.meta.url));
let nextConversation = 1;
let answerCount = 0;
function owner(state) {
  return state.guest ? state.owner : state.user_id;
}
function createConversation(userId, title = 'New conversation') {
  const chat = { id: nextConversation++, user_id: userId, title, pinned: false };
  conversations.push(chat);
  histories.set(chat.id, []);
  return chat;
}
function newConversation(state) {
  if (!state.guest) return createConversation(state.user_id);
  for (const chat of list(owner(state))) {
    conversations.splice(conversations.indexOf(chat), 1);
    histories.delete(chat.id);
    chatFiles.delete(chat.id);
  }
  Object.assign(state, { conversation_id: null, uploads: [], generated_files: [] });
  return createConversation(owner(state), 'Temporary chat');
}
function resetsAt(state) {
  const reset = state.guest ? state.guest_limited && new Date(Date.now() + 3600000).toISOString() : limits.get(state.user_id);
  return reset && Date.parse(reset) > Date.now() ? reset : null;
}
function uploadResetsAt(state) {
  const limited = !state.guest && users.find(user => user.id === state.user_id)?.email?.startsWith('uploads-') && (uploadCounts.get(state.user_id) ?? 0) >= 5;
  return limited ? new Date(Date.now() + 3600000).toISOString() : null;
}
function overLimit(state, response) {
  if (state.guest ? !state.guest_limited : !resetsAt(state)) return false;
  response.statusCode = 403;
  response.end(JSON.stringify({ detail: state.guest ? 'Guest limit reached. Log in or sign up to keep chatting.' : 'Daily limit reached.' }));
  return true;
}
function list(userId) {
  return conversations.filter(chat => chat.user_id === userId).sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.id - a.id);
}
function keepFiles(state) {
  if (state.conversation_id) chatFiles.set(state.conversation_id, { uploads: state.uploads, generated_files: state.generated_files });
}
function activate(state, chat) {
  if (state.conversation_id !== chat.id) {
    if (state.conversation_id) keepFiles(state);
    Object.assign(state, chatFiles.get(chat.id) || { uploads: [], generated_files: [] });
  }
  Object.assign(state, { conversation_id: chat.id, messages: histories.get(chat.id) });
}
function pause(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}
function replyFor(question) {
  const answers = {
    table: '| Plan | Price |\n| --- | --- |\n| Basic | $5 |\n| Pro | $9 |',
    code: 'Run this:\n\n```python\nprint("hi")\n```\n\n<b>raw html</b> [bad](javascript:alert(1)) ![tracker](https://example.com/x.png) [good](https://example.com/docs)',
  };
  if (question.startsWith('Cite')) return 'English evidence [D1]. Bằng chứng tiếng Việt [D1]. Web evidence [W1].';
  if (question.startsWith('Draw')) return 'Here is your watercolor cat.';
  if (question.startsWith('Slow')) return 'This answer arrives one slow word at a time so it can be stopped early.';
  if (question.startsWith('Again')) return `Answer number ${++answerCount}.`;
  return answers[Object.keys(answers).find(kind => question.toLowerCase().includes(`as a ${kind}`))] ?? 'Edited the file.';
}
function finishTurn(state, question, replaceFrom, reply, stopped) {
  const current = conversations.find(chat => chat.id === state.conversation_id);
  if ((replaceFrom === 0 || !state.messages.length) && current && !current.named) Object.assign(current, { title: question.slice(0, 50), named: true });
  if (state.uploads.length) state.uploads[0].edits.push({ id: randomUUID(), filename: state.uploads[0].filename });
  state.generated_files.push({ id: randomUUID(), filename: 'result.txt' });
  const kept = replaceFrom === null ? [] : state.messages[replaceFrom].attachments ?? [];
  const attachments = [...kept, ...state.uploads.filter(file => !file.sent && !kept.some(item => item.id === file.id)).map(({ id, filename }) => ({ id, filename }))];
  for (const file of state.uploads) file.sent = true;
  const images = question.startsWith('Draw') && !stopped ? [{ id: randomUUID(), filename: 'watercolor-cat.png' }] : [];
  for (const image of images) { imageNames.set(image.id, image.filename); state.generated_files.push(image); }
  keepFiles(state);
  if (replaceFrom !== null) state.messages.splice(replaceFrom);
  if (question.startsWith('Preview fixtures')) {
    state.generated_files.push(...['index.html', 'report.pdf', 'notes.md', 'budget.xlsx', 'slides.pptx', 'bundle.zip'].map(filename => ({ id: randomUUID(), filename })));
    keepFiles(state);
  }
  const sources = [{ kind: 'web', marker: 'W1', title: 'Evidence', url: 'https://example.com' }];
  if (question.startsWith('Cite') && state.uploads.length && reply.includes('[D1]')) {
    const file = state.uploads[0];
    const source = { kind: 'document', id: randomUUID(), marker: 'D1', title: file.filename, file_id: file.id,
      revision_id: file.id, revision: 'test-revision', version: 'Original', location: 'Section 1' };
    sources.unshift(source);
    sourceSnapshots.set(source.id, { ...source, text: file.text, owner: owner(state), conversation_id: state.conversation_id });
  }
  state.messages.push({ role: 'user', content: question, attachments }, { role: 'assistant', content: reply, attachments: images, stopped, rating: null, sources });
  if (state.guest) {
    state.guest_tokens += question.startsWith('Use every token') ? 50000 : Math.ceil((question.length + 16) / 4);
    state.guest_limited = state.guest_tokens >= 50000;
  } else if (question.startsWith('Use every token')) {
    limits.set(state.user_id, new Date(Date.now() + 6000).toISOString());
  }
  return { ...state, attachments: images, stopped, limit_resets_at: resetsAt(state), answer: reply, display_answer: reply, sources };
}
createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  let token = request.headers['x-guest-session'] || url.searchParams.get('guest_session') || request.headers.cookie?.match(/chat_session=([^;]+)/)?.[1];
  if (!token || !sessions.has(token)) {
    token = randomUUID();
    sessions.set(token, { user_id: null, conversation_id: null, messages: [], uploads: [], generated_files: [] });
    response.setHeader('set-cookie', `chat_session=${token}; HttpOnly; Path=/; SameSite=strict`);
  }
  const state = sessions.get(token);
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = Buffer.concat(chunks);
  response.setHeader('content-type', 'application/json');
  const json = value => response.end(JSON.stringify(value));
  const missing = () => { response.statusCode = 404; return json({ detail: 'Not found' }); };
  if (url.pathname === '/api/auth/me') return json({ user: users.find(user => user.id === state.user_id) ?? null, guest: !!state.guest });
  if (url.pathname === '/api/auth/guest') {
    const guestToken = randomUUID();
    sessions.set(guestToken, { user_id: null, owner: `guest:${guestToken}`, conversation_id: null, guest: true, guest_tokens: 0, guest_limited: false, messages: [], uploads: [], generated_files: [] });
    return json({ user: null, guest: true, guest_token: guestToken });
  }
  if (url.pathname === '/api/auth/guest/close') return json({ ok: true });
  if (url.pathname === '/api/auth/logout') {
    if (!state.guest) keepFiles(state);
    state.guest = false;
    state.guest_limited = false;
    Object.assign(state, { user_id: null, conversation_id: null, messages: [], uploads: [], generated_files: [] });
    return json({ user: null });
  }
  if (url.pathname === '/api/auth/login' || url.pathname === '/api/auth/register') {
    const payload = JSON.parse(body);
    let user = users.find(user => user.email === payload.email);
    if (url.pathname.endsWith('register') && !user) {
      user = { id: users.length + 1, name: payload.name, email: payload.email };
      users.push(user);
    }
    if (!user) { response.statusCode = 401; return json({ detail: 'Email or password is incorrect' }); }
    state.user_id = user.id;
    activate(state, list(user.id)[0] ?? createConversation(user.id));
    return json({ user });
  }
  if (url.pathname !== '/api/state' && !state.user_id && !state.guest) { response.statusCode = 401; return json({ detail: 'Log in to continue' }); }
  if (url.pathname === '/api/document/settings') return json({ max_file_bytes: 20971520, max_conversation_files: 20, max_conversation_bytes: 104857600, parsing_enabled: false, text_extensions: ['.txt', '.md', '.csv'], image_extensions: ['.png', '.jpg'], guest_inspection_enabled: !!state.guest });
  if (url.pathname === '/api/state') return json({ ...state, conversations: list(owner(state)), limit_resets_at: resetsAt(state), upload_resets_at: uploadResetsAt(state) });
  if (url.pathname.startsWith('/api/sources/')) {
    const source = sourceSnapshots.get(url.pathname.split('/').at(-1));
    if (!source || source.owner !== owner(state) || source.conversation_id !== state.conversation_id || !state.uploads.some(file => file.id === source.file_id)) return missing();
    return json(source);
  }
  if (url.pathname === '/api/users') {
    if (request.method === 'POST') {
      const user = { id: users.length + 1, name: JSON.parse(body).name };
      users.push(user);
      return json(user);
    }
    return json(users);
  }
  const select = url.pathname.match(/^\/api\/users\/(\d+)\/select$/);
  if (select) {
    const id = Number(select[1]);
    if (state.user_id !== id) {
      state.user_id = id;
      activate(state, list(id)[0] ?? createConversation(id));
    }
    return json(users.find(user => user.id === id));
  }
  if (url.pathname === '/api/conversations') {
    if (request.method === 'POST') {
      const chat = newConversation(state);
      activate(state, chat);
      return json(chat);
    }
    return json(list(owner(state)));
  }
  const action = url.pathname.match(/^\/api\/conversations\/(\d+)(\/select)?$/);
  if (action) {
    const chat = conversations.find(chat => chat.id === Number(action[1]) && chat.user_id === owner(state));
    if (!chat) return missing();
    if (action[2]) {
      activate(state, chat);
      return json(chat);
    }
    if (request.method === 'PATCH') {
      const changes = JSON.parse(body);
      Object.assign(chat, changes, changes.title === undefined ? {} : { named: true });
      return json(chat);
    }
    if (request.method === 'DELETE') {
      conversations.splice(conversations.indexOf(chat), 1);
      histories.delete(chat.id);
      chatFiles.delete(chat.id);
      if (state.conversation_id === chat.id) {
        Object.assign(state, { conversation_id: null, messages: [], uploads: [], generated_files: [] });
        if (list(owner(state)).length) activate(state, list(owner(state))[0]);
      }
      return json({ ok: true });
    }
  }
  if (url.pathname === '/api/document' && request.method === 'POST') {
    if (overLimit(state, response)) return;
    if (uploadResetsAt(state)) { response.statusCode = 403; return json({ detail: 'Daily upload limit reached (5 files a day). You can upload more files after midnight.' }); }
    if (!state.guest) uploadCounts.set(state.user_id, (uploadCounts.get(state.user_id) ?? 0) + 1);
    const form = await new Response(body, { headers: { 'content-type': request.headers['content-type'] } }).formData();
    const file = form.get('file');
    if (file.name.startsWith('slow')) await new Promise(resolve => setTimeout(resolve, 1500));
    if (!state.conversation_id) activate(state, newConversation(state));
    const upload = { id: randomUUID(), filename: file.name, text: await file.text(), status: 'Text ready for chat.', sent: false, edits: [] };
    state.uploads.push(upload);
    keepFiles(state);
    return json(upload);
  }
  if (url.pathname === '/api/document' && request.method === 'DELETE') {
    state.uploads = url.searchParams.has('file_id') ? state.uploads.filter(file => file.id !== url.searchParams.get('file_id')) : [];
    keepFiles(state);
    return json({ ok: true });
  }
  if (url.pathname === '/api/files/preview' || url.pathname === '/api/files/preview/content') {
    const file = state.generated_files.find(item => item.id === url.searchParams.get('file_id'));
    if (!file) return missing();
    if (url.pathname.endsWith('/content')) {
      response.setHeader('content-type', 'application/pdf');
      return response.end(previewPdf);
    }
    const base = { filename: file.filename, kind: 'text', text: 'Hello / Xin chào <script>not executed</script>', notice: '', truncated: false };
    if (file.filename.endsWith('.html')) Object.assign(base, { kind: 'html', text: '<!doctype html><meta http-equiv="refresh" content="0;url=https://example.com/navigate"><h1>Hello / Xin chào</h1><style>body{background:#eee} @import url(https://example.com/style);</style><script>parent.previewPwned=true</script><img src="https://example.com/track"><a href="https://example.com/link" target="_top">External link</a><form action="https://example.com/post"><button>Submit</button></form><iframe src="https://example.com/frame"></iframe>' });
    if (file.filename.endsWith('.pdf')) Object.assign(base, { kind: 'pdf' });
    if (file.filename.endsWith('.xlsx')) Object.assign(base, { kind: 'spreadsheet', sheets: [{ name: 'English', rows: [['Hello', '=1+1']] }, { name: 'Tiếng Việt', rows: [['Xin chào']] }] });
    if (file.filename.endsWith('.pptx')) Object.assign(base, { kind: 'slides', slides: [{ name: 'Slide 1', text: 'Hello / Xin chào' }] });
    if (file.filename.endsWith('.zip')) Object.assign(base, { kind: 'archive', entries: [{ name: 'README.md', size: 100 }] });
    return json(base);
  }
  if (url.pathname === '/api/export') {
    const payload = JSON.parse(body);
    response.setHeader('content-type', 'application/octet-stream');
    response.setHeader('content-disposition', `attachment; filename="aster-answer.${payload.format}"`);
    return response.end(payload.content);
  }
  if (url.pathname === '/api/chat' || url.pathname === '/api/chat/stream') {
    const payload = JSON.parse(body);
    if (overLimit(state, response)) return;
    if (!state.conversation_id) activate(state, newConversation(state));
    const replaceFrom = payload.replace_from ?? null;
    if (replaceFrom !== null && state.messages[replaceFrom]?.role !== 'user') return missing();
    const reply = replyFor(payload.message);
    if (url.pathname === '/api/chat') return json(finishTurn(state, payload.message, replaceFrom, reply, false));
    response.setHeader('content-type', 'text/event-stream');
    const send = event => response.write(`data: ${JSON.stringify(event)}\n\n`);
    Object.assign(state, { streaming: true, stopRequested: false });
    if (state.uploads.some(file => !file.sent)) {
      send({ type: 'text', text: 'Let me look. ' });
      await pause(100);
      send({ type: 'step', label: `Reading ${state.uploads.find(file => !file.sent).filename}` });
      await pause(payload.message.startsWith('Slow') ? 1000 : 150);
    }
    let written = '';
    for (const part of reply.match(/\S+\s*/g) ?? [reply]) {
      if (state.stopRequested) break;
      send({ type: 'text', text: part });
      written += part;
      await pause(payload.message.startsWith('Slow') ? 400 : 10);
    }
    const stopped = state.stopRequested;
    state.streaming = false;
    send({ type: 'done', ...finishTurn(state, payload.message, replaceFrom, stopped ? written.trim() : reply, stopped) });
    return response.end();
  }
  if (url.pathname === '/api/chat/stop') {
    state.stopRequested = !!state.streaming;
    return json({ stopped: state.stopRequested });
  }
  if (url.pathname === '/api/chat/rating') {
    const { index, rating } = JSON.parse(body);
    const item = state.messages[index];
    if (item?.role !== 'assistant') return missing();
    item.rating = rating;
    return json({ rating });
  }
  const imageName = imageNames.get(url.searchParams.get('file_id'));
  if (url.pathname === '/api/files/view' || (url.pathname === '/api/files/download' && imageName)) {
    if (!imageName) return missing();
    response.setHeader('content-type', url.pathname.endsWith('/view') ? 'image/png' : 'application/octet-stream');
    if (url.pathname.endsWith('/download')) response.setHeader('content-disposition', `attachment; filename="${imageName}"`);
    return response.end(pixel);
  }
  if (url.pathname.endsWith('/download') || url.pathname.endsWith('/edited')) {
    response.setHeader('content-type', 'application/octet-stream');
    response.setHeader('content-disposition', 'attachment; filename="note.txt"');
    return response.end('downloaded copy');
  }
  missing();
}).listen(8101, '127.0.0.1');
