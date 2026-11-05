import unittest
from tinycoder.session024 import delete_context


class Session024Tests(unittest.TestCase):
    def test_transfer_pattern_not_complete_target_answer(self):
        prefix,suffix=delete_context()
        self.assertIn("store.delete(req.params.id)",prefix)
        self.assertIn("'/api/notes/:id'",prefix)
        self.assertNotIn("res.json({deleted:store.delete",prefix+suffix)
        self.assertTrue(suffix.startswith('}));'))


if __name__=='__main__':unittest.main()
