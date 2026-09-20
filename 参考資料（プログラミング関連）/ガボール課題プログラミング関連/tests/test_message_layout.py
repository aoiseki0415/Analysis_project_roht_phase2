import unittest

from utils.message_layout import message_font_size_px


class MessageFontSizeTests(unittest.TestCase):
    def test_short_message_uses_maximum_on_large_screen(self):
        self.assertEqual(42, message_font_size_px(1500, 900, "開始します。\n押してください。"))

    def test_long_message_shrinks_on_half_width_screen(self):
        text = (
            "画面の円周上を、垂直の縞模様が移動します。\n"
            "模様が左右に傾いたら、できる限り素早く\n"
            "スペースキーを押して回答してください。"
        )
        size = message_font_size_px(700, 850, text)
        self.assertGreaterEqual(size, 24)
        self.assertLess(size, 42)

    def test_explicit_line_breaks_allow_larger_text(self):
        one_line = "あ" * 40
        two_lines = "あ" * 20 + "\n" + "あ" * 20
        self.assertGreater(
            message_font_size_px(700, 850, two_lines),
            message_font_size_px(700, 850, one_line),
        )

    def test_invalid_geometry_returns_minimum(self):
        self.assertEqual(24, message_font_size_px(0, 850, "test"))


if __name__ == "__main__":
    unittest.main()
