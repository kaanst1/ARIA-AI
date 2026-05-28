"""Test konfigürasyonu — src dizinini Python path'ine ekle."""

import sys
from pathlib import Path

# src-layout: testler ARIA paketini import edebilmeli
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
