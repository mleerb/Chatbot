import assert from 'node:assert/strict';
import test from 'node:test';
import { citationMarkdown, draftText } from '../lib/citations';
import type { Source } from '../lib/api';

const sources: Source[] = [
  { kind: 'document', id: 'one', marker: 'D1', title: 'Chính sách.txt', file_id: 'file', revision_id: 'original', revision: 'hash', version: 'Original', location: 'Section 1' },
  { kind: 'web', marker: 'W1', title: 'Web', url: 'https://example.com' },
];

test('document and web citations have separate validated targets in English and Vietnamese', () => {
  assert.equal(citationMarkdown('English [D1]. Tiếng Việt [W1]. Unknown [D99] [W99].', sources),
    'English [D1](/__aster_citation/D1). Tiếng Việt [W1](/__aster_citation/W1). Unknown  .');
});

test('citation syntax in fenced and inline code is not turned into buttons', () => {
  const code = '```txt\n[D1]\n```\n`[W1]`\n~~~text\n[D1]\n~~~';
  assert.equal(citationMarkdown(code, sources), code);
});

test('streaming drafts never render citation buttons or incomplete trailing markers', () => {
  for (const ending of ['[', '[D', '[D1', '[W', '[W1']) {
    assert.equal(draftText('English / Tiếng Việt ' + ending), 'English / Tiếng Việt ');
  }
  assert.equal(draftText('English [D1] / Tiếng Việt [W1]'), 'English  / Tiếng Việt ');
  assert.equal(citationMarkdown('Unvalidated [D1]', []), 'Unvalidated ');
});
