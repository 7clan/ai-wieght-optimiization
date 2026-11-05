import unittest

from tinycoder.session022 import DEFAULT, normalize, slot_context, valid_for
from tinycoder.session022_contract import SLOTS, SLOT_TO_ROLE, TEMPLATES, assemble


class Session022Tests(unittest.TestCase):
    def test_slots_match_templates(self):
        self.assertEqual(set(SLOTS),set(SLOT_TO_ROLE))
        self.assertEqual(set(assemble(DEFAULT)),set(TEMPLATES))
        self.assertFalse(any('[[' in s for s in assemble(DEFAULT).values()))

    def test_slot_context_points_to_exact_hole(self):
        for slot in SLOTS:
            with self.subTest(slot=slot):
                before,after=slot_context(DEFAULT,slot)
                self.assertEqual((before+DEFAULT[slot]+after),assemble(DEFAULT)[SLOT_TO_ROLE[slot]])

    def test_trimming_does_not_replace_semantics(self):
        self.assertEqual(normalize('{tasks:store.list()}));\nwhatever','api_get'),
                         '{tasks:store.list()}')
        self.assertEqual(normalize('total-completed\nnext line','logic_completed'),
                         'total-completed')

    def test_summary_requires_real_integration(self):
        record={'checks':{'summary':True,'integrated_api':False},
                'modules':{'api':{'passed':True}}}
        self.assertFalse(valid_for('api_summary',record,'{total:0}'))

    def test_no_empty_css_can_be_accepted(self):
        record={'checks':{},'modules':{'css':{'passed':True}}}
        self.assertFalse(valid_for('css_theme',record,''))
        self.assertFalse(valid_for('css_theme',record,'a { background:url(https://bad); }'))


if __name__=='__main__':unittest.main()
