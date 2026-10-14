"""Retired barcode-only fallback healer; use the verified review queue runner."""


def heal_items():
    raise RuntimeError('Unsafe fallback healing is retired. Use scripts/reprocess_rabuta_verified.py with native-source polygons and identity evidence.')


if __name__ == '__main__':
    raise SystemExit('Unsafe fallback healing is retired. Use scripts/reprocess_rabuta_verified.py; delivery images will not be overwritten.')
