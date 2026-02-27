import unittest


class _DummySplash:
    def update_status(self, _text):
        return None


class SmokeTests(unittest.TestCase):
    def test_import_app_and_core_services(self):
        import app  # noqa: F401
        from core.publisher import PublisherService
        from core.transcription import TranscriptionService
        from core.verification import VerificationService
        from core.writer import WriterService

        self.assertIsNotNone(TranscriptionService)
        self.assertIsNotNone(WriterService)
        self.assertIsNotNone(VerificationService)
        self.assertIsNotNone(PublisherService)

    def test_load_resources_exposes_symbols(self):
        import ui.splash as splash_loader

        splash_loader.load_resources(_DummySplash())

        self.assertIsNotNone(splash_loader.TranscriptionService)
        self.assertIsNotNone(splash_loader.WriterService)
        self.assertIsNotNone(splash_loader.PublisherService)
        self.assertIsNotNone(splash_loader.VerificationService)


if __name__ == "__main__":
    unittest.main()

