# -*- coding: utf-8 -*-
"""
MERK-3F без вкладки 231-AT-01.

Точка входа для сборки с двумя вкладками: ART и AR. Код вкладок общий с
srt_mod_spi — здесь только урезанный состав, чтобы не держать вторую копию
программы.
"""

import sys

from srt_mod_spi import main

if __name__ == "__main__":
    sys.exit(main(("ART", "AR")))
