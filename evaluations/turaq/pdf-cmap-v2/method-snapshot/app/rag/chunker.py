"""Bounded, overlapping slices of the original text, with source coordinates."""

import re
from bisect import bisect_right


class TextChunker:
    """Never normalize, reconstruct sentences, or edit numbers while chunking.

    Numeric tokens that fit within chunk_size are kept intact. A single token
    longer than chunk_size necessarily spans chunks.
    """

    version = "source-slices-v2"
    _numbers = re.compile(r"[+−－＋-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)[%％]?")

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        if (
            type(chunk_size) is not int
            or type(overlap) is not int
            or chunk_size <= 0
            or not 0 <= overlap < chunk_size
        ):
            raise ValueError("chunk_size must be positive and 0 <= overlap < chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def _spans(self, text, strategy):
        if strategy not in {"simple", "paragraph", "smart"}:
            raise ValueError(f"未知的分割策略: {strategy}")
        numbers = [
            (m.start(), m.end())
            for m in self._numbers.finditer(text)
            if m.end() - m.start() <= self.chunk_size
        ]
        starts = [s for s, _ in numbers]

        def containing(position):
            i = bisect_right(starts, position) - 1
            if i >= 0 and numbers[i][0] < position < numbers[i][1]:
                return numbers[i]
            return None

        pattern = r"\n[ \t\r]*\n+" if strategy == "paragraph" else r"\n+|[。！？!?；;.]|\s+"
        boundaries = [] if strategy == "simple" else [m.end() for m in re.finditer(pattern, text)]
        spans = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            if end < len(text):
                i = bisect_right(boundaries, end) - 1
                minimum = start + max(self.overlap + 1, int(self.chunk_size * 0.6))
                if i >= 0 and boundaries[i] >= minimum:
                    end = boundaries[i]
                token = containing(end)
                if token:
                    end = token[0] if token[0] > start else token[1]
            if text[start:end].strip():
                spans.append((start, end))
            if end == len(text):
                break
            next_start = max(start + 1, end - self.overlap)
            token = containing(next_start)
            if token:
                next_start = token[0] if token[0] > start else token[1]
            start = next_start
        return spans

    def chunk(self, text: str, strategy: str = "smart") -> list[str]:
        return [text[start:end] for start, end in self._spans(text, strategy)]

    def chunk_with_metadata(
        self, text: str, source: str = "", strategy: str = "smart"
    ) -> list[dict]:
        spans = self._spans(text, strategy)
        return [
            dict(
                text=text[start:end],
                chunk_index=i,
                total_chunks=len(spans),
                source=source,
                char_count=end - start,
                char_start=start,
                char_end=end,
                chunker_version=self.version,
            )
            for i, (start, end) in enumerate(spans)
        ]
