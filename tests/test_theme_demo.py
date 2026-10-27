import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'examples' / 'python'))
import theme_demo  # noqa: E402


class ThemeDemoTests(unittest.TestCase):
    def test_theme_fixture_flows_only_through_scene_tokens_and_static_actions(self):
        theme = theme_demo.sample_theme()
        scene = theme_demo.build_scene(theme)
        self.assertEqual(scene['theme'], theme)
        actions = {
            node['props'].get('action')
            for node in scene['root']['children'][-1]['children']
        }
        self.assertEqual(actions, {'theme.apply', 'theme.default', 'theme.invalid'})
        self.assertNotIn('css', scene)
        self.assertNotIn('script', scene)

    def test_default_scene_has_no_provider_theme(self):
        scene = theme_demo.build_scene(None, 'Host default theme')
        self.assertNotIn('theme', scene)
        self.assertIn('Host default theme', str(scene))

    def test_invalid_theme_probe_preserves_all_other_tokens(self):
        theme = theme_demo.sample_theme()
        invalid = theme_demo.invalid_theme(theme)
        self.assertEqual(invalid['foreground'], invalid['background'])
        self.assertEqual(invalid['accent'], theme['accent'])
        self.assertEqual(invalid['font_scale'], theme['font_scale'])
        self.assertEqual(theme['foreground'], '#F9FAFB')


if __name__ == '__main__':
    unittest.main()
