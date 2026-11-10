"""この Blender から始めて、まだ終わっていない仕事を小さな JSON に残す（11/9、アドオン 0.1.11）。

今まで job_id はメモリにしか無く、Blender を閉じる・アドオンを入れ直すと追えなくなっていた。ここに残すので、次に起動した
ときに続きを追って成果物を受け取れる。job_id がまだ分からない間（投入の返事を受け取る前に落ちた）は Idempotency-Key を
残す。同じ鍵で投入し直すと受付は最初の仕事を返すので、二重には入らない。

API キーはここに書かない（設定に 1 か所だけ）。bpy を使わないので Blender なしで試せる。
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

# 成果物は最長 7 日残る（前払いの鍵）。それより古い行は読むときに捨てる
KEEP_SECONDS = 8 * 86400


class Store:
    """行は {"idem", "kind", "server", "scene_id", "job_id", "body", "out_dir", "open_when_done", "created", "blend"}。"""

    def __init__(self, path: "str | Path") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._rows: Optional[list[dict[str, Any]]] = None

    def _load(self) -> list[dict[str, Any]]:
        if self._rows is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                rows = data.get("jobs") if isinstance(data, dict) else None
                self._rows = [r for r in rows or [] if isinstance(r, dict) and r.get("idem")]
            except (OSError, ValueError):
                self._rows = []
        now = time.time()
        self._rows = [r for r in self._rows if now - float(r.get("created") or 0) < KEEP_SECONDS]
        return self._rows

    def _save(self) -> None:
        rows = self._rows or []
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({"jobs": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass                    # 書けなくても描画は続ける（再起動の後に追えないだけ）

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._load()]

    def get(self, idem: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return next((dict(r) for r in self._load() if r.get("idem") == idem), None)

    def put(self, row: dict[str, Any]) -> None:
        with self._lock:
            rows = [r for r in self._load() if r.get("idem") != row.get("idem")]
            rows.append({"created": time.time(), **row})
            self._rows = rows
            self._save()

    def update(self, idem: str, **fields: Any) -> None:
        with self._lock:
            for r in self._load():
                if r.get("idem") == idem:
                    r.update(fields)
                    self._save()
                    return

    def remove(self, idem: str) -> None:
        with self._lock:
            rows = self._load()
            keep = [r for r in rows if r.get("idem") != idem]
            if len(keep) != len(rows):
                self._rows = keep
                self._save()
