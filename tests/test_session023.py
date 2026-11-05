import unittest

from tinycoder.session023_contract import (SLOTS, TEMPLATES,
    TEACHER_LESSONS, REFERENCE_INNER, assemble, coached_context)


class MentorProtocolTests(unittest.TestCase):
    def test_teacher_scaffold_has_no_missing_slots(self):
        source=assemble(REFERENCE_INNER)
        self.assertEqual(set(source),{'logic','api','ui','css'})
        self.assertNotIn('[[',source['api'])
        self.assertIn('res.json({tasks:store.list()})',source['api'])

    def test_fim_prompt_contains_analogy_not_target_answer(self):
        for slot,lesson in TEACHER_LESSONS.items():
            with self.subTest(slot=slot):
                prefix,suffix=coached_context(slot)
                self.assertIn(lesson['analogy'],prefix)
                self.assertNotIn(lesson['corrected'],prefix+suffix)
                self.assertIn('return app;',suffix)

    def test_api_wrappers_require_semantic_expressions(self):
        for slot in TEACHER_LESSONS:
            before,after=coached_context(slot)
            self.assertIn('store',before)
            self.assertIn('));',after)


if __name__=='__main__':unittest.main()
