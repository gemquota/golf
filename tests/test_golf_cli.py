import unittest

import golf


class GolfCliTests(unittest.TestCase):
    def test_scrape_command_has_full_pipeline_by_default(self):
        args = golf.build_parser().parse_args(["scrape"])
        self.assertEqual(args.command, "scrape")
        self.assertFalse(args.no_pipeline)
        self.assertFalse(args.no_publish)

    def test_scrape_only_is_explicit(self):
        args = golf.build_parser().parse_args(["scrape", "--no-pipeline"])
        self.assertTrue(args.no_pipeline)

    def test_interactive_command_preserves_resume_option(self):
        args = golf.build_parser().parse_args(["interactive", "-r", "-s"])
        self.assertTrue(args.resume)
        self.assertTrue(args.shuffle)

    def test_pipeline_does_not_publish_by_default_override(self):
        args = golf.build_parser().parse_args(["pipeline", "--no-publish"])
        self.assertTrue(args.no_publish)

    def test_export_and_publish_are_distinct_commands(self):
        self.assertEqual(golf.build_parser().parse_args(["export"]).command, "export")
        self.assertEqual(golf.build_parser().parse_args(["publish"]).command, "publish")


if __name__ == "__main__":
    unittest.main()
