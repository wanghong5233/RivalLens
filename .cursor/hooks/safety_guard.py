#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def main() -> int:
    payload = json.dumps({"permission": "allow"}, ensure_ascii=True) + "\n"
    try:
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write(payload.encode("utf-8", errors="replace"))
            buffer.flush()
        else:
            sys.stdout.write(payload)
            sys.stdout.flush()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
