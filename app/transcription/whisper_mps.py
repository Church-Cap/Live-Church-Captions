"""Compatibility for Whisper word alignment on Apple Metal."""
from functools import wraps


def enable_mps_alignment() -> None:
    """Move only the alignment matrix to CPU before Whisper converts to float64.

    Whisper 20250625's DTW fallback calls x.double().cpu(). MPS cannot create
    float64 tensors, so transfer first. Keep model inference on MPS and retain
    word timestamps; leave Whisper's CPU and CUDA paths unchanged.
    """
    from whisper import timing

    original = timing.dtw
    if getattr(original, '_churchcap_mps_alignment', False):
        return

    @wraps(original)
    def dtw_with_mps_transfer(matrix):
        if matrix.device.type == 'mps':
            matrix = matrix.cpu()
        return original(matrix)

    dtw_with_mps_transfer._churchcap_mps_alignment = True
    timing.dtw = dtw_with_mps_transfer
