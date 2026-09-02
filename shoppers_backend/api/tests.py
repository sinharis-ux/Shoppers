from django.test import SimpleTestCase

from .virtual_tryon_service import (
    build_garment_intent,
    build_tryon_guidance,
    select_tryon_person_path,
)


class TryOnIntentTests(SimpleTestCase):
    def test_first_top_uses_avatar_path(self):
        path, source, used_compounding = select_tryon_person_path(
            "/media/avatar.jpg",
            None,
            "top",
            path_exists=lambda path: path == "/media/avatar.jpg",
        )

        self.assertEqual(path, "/media/avatar.jpg")
        self.assertEqual(source, "avatar")
        self.assertFalse(used_compounding)

    def test_first_bottom_uses_avatar_path(self):
        path, source, used_compounding = select_tryon_person_path(
            "/media/avatar.jpg",
            None,
            "bottom",
            path_exists=lambda path: path == "/media/avatar.jpg",
        )

        self.assertEqual(path, "/media/avatar.jpg")
        self.assertEqual(source, "avatar")
        self.assertFalse(used_compounding)

    def test_top_after_bottom_uses_latest_tryon_path(self):
        path, source, used_compounding = select_tryon_person_path(
            "/media/avatar.jpg",
            "/media/tryon_pants.jpg",
            "top",
            path_exists=lambda path: path in {"/media/avatar.jpg", "/media/tryon_pants.jpg"},
        )

        self.assertEqual(path, "/media/tryon_pants.jpg")
        self.assertEqual(source, "latest_tryon")
        self.assertTrue(used_compounding)

    def test_bottom_after_top_uses_latest_tryon_path(self):
        path, source, used_compounding = select_tryon_person_path(
            "/media/avatar.jpg",
            "/media/tryon_shirt.jpg",
            "bottom",
            path_exists=lambda path: path in {"/media/avatar.jpg", "/media/tryon_shirt.jpg"},
        )

        self.assertEqual(path, "/media/tryon_shirt.jpg")
        self.assertEqual(source, "latest_tryon")
        self.assertTrue(used_compounding)

    def test_outfit_ignores_latest_tryon_path(self):
        path, source, used_compounding = select_tryon_person_path(
            "/media/avatar.jpg",
            "/media/tryon_shirt.jpg",
            "outfit",
            path_exists=lambda path: path in {"/media/avatar.jpg", "/media/tryon_shirt.jpg"},
        )

        self.assertEqual(path, "/media/avatar.jpg")
        self.assertEqual(source, "avatar")
        self.assertFalse(used_compounding)

    def test_missing_category_does_not_compound(self):
        path, source, used_compounding = select_tryon_person_path(
            "/media/avatar.jpg",
            "/media/tryon_shirt.jpg",
            "",
            path_exists=lambda path: path in {"/media/avatar.jpg", "/media/tryon_shirt.jpg"},
        )

        self.assertEqual(path, "/media/avatar.jpg")
        self.assertEqual(source, "avatar")
        self.assertFalse(used_compounding)

    def test_button_category_wins_for_top(self):
        intent = build_garment_intent("top", "Relaxed fit denim jeans")

        self.assertEqual(intent["action"], "top")
        self.assertEqual(intent["model_category"], "Upper-body")
        self.assertEqual(intent["subtype"], "jeans")

    def test_shorts_guidance(self):
        intent = build_garment_intent("bottom", "Black athletic shorts")
        guidance = build_tryon_guidance(intent)

        self.assertEqual(intent["action"], "bottom")
        self.assertEqual(intent["subtype"], "shorts")
        self.assertIn("Shorts must end above the knee", guidance)

    def test_jeans_guidance(self):
        intent = build_garment_intent("bottom", "Blue denim jeans")
        guidance = build_tryon_guidance(intent)

        self.assertEqual(intent["subtype"], "jeans")
        self.assertEqual(intent["hem_length"], "full-length")
        self.assertIn("do not turn jeans or pants into shorts", guidance)

    def test_sleeve_guidance(self):
        short_sleeve = build_garment_intent("top", "Half sleeve cotton t-shirt")
        full_sleeve = build_garment_intent("top", "Full sleeve formal shirt")

        self.assertEqual(short_sleeve["sleeve_length"], "short")
        self.assertIn("forearms must remain bare skin", build_tryon_guidance(short_sleeve))
        self.assertEqual(full_sleeve["sleeve_length"], "long")
        self.assertIn("extend naturally to the wrists", build_tryon_guidance(full_sleeve))

    def test_outfit_dress_uses_one_piece_category(self):
        intent = build_garment_intent("outfit", "Floral maxi dress")

        self.assertEqual(intent["action"], "outfit")
        self.assertEqual(intent["model_category"], "Dress")
        self.assertEqual(intent["subtype"], "dress")
