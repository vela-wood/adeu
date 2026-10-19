/**
 * A replacement whose new text starts with a block marker ("1. ", "* ", "# ")
 * and spans a paragraph break stranded the host paragraph's trailing text
 * before the new paragraphs instead of carrying it along. Mid-paragraph, the
 * marker is literal text, not a block.
 *
 * Mirror of python/tests/test_repro_block_marker_suffix.py.
 */
import { describe, it, expect } from 'vitest';
import { createTestDocument, addParagraph } from './test-utils.js';
import { extractTextFromBuffer } from './ingest.js';
import { generate_edits_via_paragraph_alignment } from './diff.js';
import { RedlineEngine } from './engine.js';

async function roundtrip(original: string, target: string): Promise<string> {
  const doc = await createTestDocument();
  addParagraph(doc, original);
  const clean = await extractTextFromBuffer(await doc.save(), true);

  const edits = generate_edits_via_paragraph_alignment(clean, target);
  const engine = new RedlineEngine(doc, 'Test');
  const stats = engine.process_batch(edits as any);
  expect(stats.edits_skipped).toBe(0);

  engine.accept_all_revisions(true);
  return extractTextFromBuffer(await doc.save(), true);
}

describe('Block marker replacements keep host text in order', () => {
  // "1. " cases use "* " here: "List Number" is style-only (AI_CONTEXT
  // section 11) and initial.docx defines no ListNumber style, so its marker
  // cannot project back. Same block-mode path.
  it.each([
    ['0 1.', '* 0\n\n0.'],
    ['a b.', '* a\n\nb.'],
    ['a b.', '# a\n\nb.'],
  ])('suffix follows the new block: %j -> %j', async (original, target) => {
    expect(await roundtrip(original, target)).toBe(target);
  });

  it.each([
    ['0 0 1.', '0 1. 0\n\n0.'],
    ['x a b.', 'x 1. a\n\nb.'],
    ['x a', 'x 1. a\n\nb'],
  ])('mid-paragraph marker is literal: %j -> %j', async (original, target) => {
    expect(await roundtrip(original, target)).toBe(target);
  });
});
