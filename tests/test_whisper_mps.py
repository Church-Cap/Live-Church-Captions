import unittest
from unittest.mock import Mock, patch

import numpy as np
import torch
import whisper.timing as timing

from app.transcription.whisper_live import WhisperLiveTranscriber
from app.transcription.whisper_mps import enable_mps_alignment


class WhisperMpsTests(unittest.TestCase):
    def setUp(self):
        original = timing.dtw
        self.addCleanup(setattr, timing, 'dtw', original)

    def test_installation_is_idempotent_and_preserves_cpu_alignment(self):
        tensor = torch.arange(32, dtype=torch.float32).reshape(4, 8)
        expected = timing.dtw(tensor)
        enable_mps_alignment()
        installed = timing.dtw
        enable_mps_alignment()
        self.assertIs(timing.dtw, installed)
        actual = timing.dtw(tensor)
        for before, after in zip(expected, actual):
            np.testing.assert_array_equal(before, after)

    def test_mps_transfer_happens_before_whisper_float64_conversion(self):
        cpu_tensor = torch.arange(32, dtype=torch.float32).reshape(4, 8)
        expected = timing.dtw(cpu_tensor)
        mps_tensor = Mock()
        mps_tensor.device.type = 'mps'
        mps_tensor.cpu.return_value = cpu_tensor
        enable_mps_alignment()
        actual = timing.dtw(mps_tensor)
        mps_tensor.cpu.assert_called_once_with()
        mps_tensor.double.assert_not_called()
        for before, after in zip(expected, actual):
            np.testing.assert_array_equal(before, after)

    @unittest.skipUnless(torch.backends.mps.is_available(), 'Requires Apple Metal')
    def test_mps_alignment_matches_cpu_without_float64_on_mps(self):
        tensor = torch.arange(32, dtype=torch.float32).reshape(4, 8)
        expected = timing.dtw(tensor)
        enable_mps_alignment()
        actual = timing.dtw(tensor.to('mps'))
        for before, after in zip(expected, actual):
            np.testing.assert_array_equal(before, after)

    @unittest.skipUnless(torch.backends.mps.is_available(), 'Requires Apple Metal')
    def test_model_loader_enables_compatibility_for_word_timestamps(self):
        transcriber = WhisperLiveTranscriber.__new__(WhisperLiveTranscriber)
        transcriber._model = None
        transcriber.model_name = 'base'
        transcriber.device = 'mps'
        with patch('whisper.load_model', return_value=object()):
            transcriber._load_model()
        timing.dtw(torch.zeros(4, 8, device='mps', dtype=torch.float32))
        self.assertEqual(transcriber.device, 'mps')
