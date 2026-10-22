import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';

const sessions = new Map();
const users = [{ id: 1, name: 'Tester', email: 'tester@example.com' }, { id: 2, name: 'Other', email: 'other@example.com' }];
const conversations = [];
const histories = new Map();
const chatFiles = new Map();
let nextConversation = 1;
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
function overLimit(state, response) {
  if (!state.guest || !state.guest_limited) return false;
  response.statusCode = 403;
  response.end(JSON.stringify({ detail: 'Guest limit reached. Log in or sign up to keep chatting.' }));
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
  if (url.pathname === '/api/state') return json({ ...state, conversations: list(owner(state)) });
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
    const form = await new Response(body, { headers: { 'content-type': request.headers['content-type'] } }).formData();
    const file = form.get('file');
    if (file.name.startsWith('slow')) await new Promise(resolve => setTimeout(resolve, 1500));
    if (!state.conversation_id) activate(state, newConversation(state));
    const upload = { id: randomUUID(), filename: file.name, status: 'Text ready for chat.', sent: false, edits: [] };
    state.uploads.push(upload);
    keepFiles(state);
    return json(upload);
  }
  if (url.pathname === '/api/document' && request.method === 'DELETE') {
    state.uploads = url.searchParams.has('file_id') ? state.uploads.filter(file => file.id !== url.searchParams.get('file_id')) : [];
    keepFiles(state);
    return json({ ok: true });
  }
  if (url.pathname === '/api/export') {
    const payload = JSON.parse(body);
    response.setHeader('content-type', 'application/octet-stream');
    response.setHeader('content-disposition', `attachment; filename="aster-answer.${payload.format}"`);
    return response.end(payload.content);
  }
  if (url.pathname === '/api/chat') {
    const question = JSON.parse(body).message;
    if (overLimit(state, response)) return;
    if (!state.conversation_id) activate(state, newConversation(state));
    const current = conversations.find(chat => chat.id === state.conversation_id);
    if (!state.messages.length && current && !current.named) Object.assign(current, { title: question.slice(0, 50), named: true });
    if (state.uploads.length) state.uploads[0].edits.push({ id: randomUUID(), filename: state.uploads[0].filename });
    state.generated_files.push({ id: randomUUID(), filename: 'result.txt' });
    keepFiles(state);
    const attachments = state.uploads.filter(file => !file.sent).map(({ id, filename }) => ({ id, filename }));
    for (const file of state.uploads) file.sent = true;
    const answers = {
      table: '| Plan | Price |\n| --- | --- |\n| Basic | $5 |\n| Pro | $9 |',
      code: 'Run this:\n\n```python\nprint("hi")\n```\n\n<b>raw html</b> [bad](javascript:alert(1)) ![tracker](https://example.com/x.png) [good](https://example.com/docs)',
    };
    const reply = answers[Object.keys(answers).find(kind => question.toLowerCase().includes(`as a ${kind}`))] ?? 'Edited the file.';
    state.messages.push({ role: 'user', content: question, attachments }, { role: 'assistant', content: reply });
    if (state.guest) {
      state.guest_tokens += question.startsWith('Use every token') ? 50000 : Math.ceil((question.length + 16) / 4);
      state.guest_limited = state.guest_tokens >= 50000;
    }
    return json({ ...state, answer: reply, display_answer: reply, sources: [{ title: 'Evidence', url: 'https://example.com' }] });
  }
  if (url.pathname.endsWith('/download') || url.pathname.endsWith('/edited')) {
    response.setHeader('content-type', 'application/octet-stream');
    response.setHeader('content-disposition', 'attachment; filename="note.txt"');
    return response.end('downloaded copy');
  }
  missing();
}).listen(8101, '127.0.0.1');
