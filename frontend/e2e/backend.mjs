import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';

const sessions = new Map();
const users = [{ id: 1, name: 'Tester' }, { id: 2, name: 'Other' }];
const conversations = [];
const histories = new Map();
let nextConversation = 1;
function createConversation(userId) {
  const chat = { id: nextConversation++, user_id: userId, title: 'New conversation', pinned: false };
  conversations.push(chat);
  histories.set(chat.id, []);
  return chat;
}
function list(userId) {
  return conversations.filter(chat => chat.user_id === userId).sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.id - a.id);
}
function activate(state, chat) {
  if (state.conversation_id !== chat.id) Object.assign(state, { uploads: [], generated_files: [] });
  Object.assign(state, { conversation_id: chat.id, messages: histories.get(chat.id) });
}
createServer(async (request, response) => {
  let token = request.headers.cookie?.match(/chat_session=([^;]+)/)?.[1];
  if (!token || !sessions.has(token)) {
    token = randomUUID();
    sessions.set(token, { user_id: null, conversation_id: null, messages: [], uploads: [], generated_files: [] });
    response.setHeader('set-cookie', `chat_session=${token}; HttpOnly; Path=/; SameSite=strict`);
  }
  const state = sessions.get(token);
  const url = new URL(request.url, 'http://localhost');
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = Buffer.concat(chunks);
  response.setHeader('content-type', 'application/json');
  const json = value => response.end(JSON.stringify(value));
  const missing = () => { response.statusCode = 404; return json({ detail: 'Not found' }); };
  if (url.pathname === '/api/state') return json({ ...state, conversations: list(state.user_id) });
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
      const chat = createConversation(state.user_id);
      activate(state, chat);
      return json(chat);
    }
    return json(list(state.user_id));
  }
  const action = url.pathname.match(/^\/api\/conversations\/(\d+)(\/select)?$/);
  if (action) {
    const chat = conversations.find(chat => chat.id === Number(action[1]) && chat.user_id === state.user_id);
    if (!chat) return missing();
    if (action[2]) {
      activate(state, chat);
      return json(chat);
    }
    if (request.method === 'PATCH') {
      Object.assign(chat, JSON.parse(body));
      return json(chat);
    }
    if (request.method === 'DELETE') {
      conversations.splice(conversations.indexOf(chat), 1);
      histories.delete(chat.id);
      if (state.conversation_id === chat.id) {
        Object.assign(state, { conversation_id: null, messages: [], uploads: [], generated_files: [] });
        if (list(state.user_id).length) activate(state, list(state.user_id)[0]);
      }
      return json({ ok: true });
    }
  }
  if (url.pathname === '/api/document' && request.method === 'POST') {
    const form = await new Response(body, { headers: { 'content-type': request.headers['content-type'] } }).formData();
    const file = form.get('file');
    const upload = { id: randomUUID(), filename: file.name, status: 'Text ready for chat.', edits: [] };
    state.uploads.push(upload);
    return json(upload);
  }
  if (url.pathname === '/api/document' && request.method === 'DELETE') {
    state.uploads = url.searchParams.has('file_id') ? state.uploads.filter(file => file.id !== url.searchParams.get('file_id')) : [];
    return json({ ok: true });
  }
  if (url.pathname === '/api/chat') {
    const question = JSON.parse(body).message;
    if (!state.conversation_id) activate(state, createConversation(state.user_id));
    if (state.uploads.length) state.uploads[0].edits.push({ id: randomUUID(), filename: state.uploads[0].filename });
    state.generated_files.push({ id: randomUUID(), filename: 'result.txt' });
    state.messages.push({ role: 'user', content: question }, { role: 'assistant', content: 'Edited the file.' });
    return json({ ...state, answer: 'Edited the file.', display_answer: 'Edited the file.', sources: [{ title: 'Evidence', url: 'https://example.com' }] });
  }
  if (url.pathname.endsWith('/download') || url.pathname.endsWith('/edited')) {
    response.setHeader('content-type', 'application/octet-stream');
    response.setHeader('content-disposition', 'attachment; filename="note.txt"');
    return response.end('downloaded copy');
  }
  missing();
}).listen(8101, '127.0.0.1');
