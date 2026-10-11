from __future__ import annotations

from collections.abc import Sequence

import tiktoken


class TiktokenTokenizer:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)

    def encode(self, text: str) -> tuple[int, ...]:
        return tuple(self._encoding.encode(text, disallowed_special=()))

    def decode(self, tokens: Sequence[int]) -> str:
        return self._encoding.decode(list(tokens))

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))

    def split_text(self, text: str, max_tokens: int) -> tuple[str, ...]:
        if max_tokens <= 0:
            raise ValueError("Maximum tokens must be positive")
        tokens = self.encode(text)
        if not tokens:
            return (text,)
        pieces: list[str] = []
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            while end > start:
                try:
                    piece = self._token_bytes(tokens[start:end]).decode("utf-8")
                    break
                except UnicodeDecodeError:
                    end -= 1
            else:
                end = min(start + max_tokens, len(tokens)) + 1
                while end <= len(tokens):
                    try:
                        piece = self._token_bytes(tokens[start:end]).decode("utf-8")
                        break
                    except UnicodeDecodeError:
                        end += 1
                else:
                    piece = self._token_bytes(tokens[start:]).decode("utf-8")
                    end = len(tokens)
            pieces.append(piece)
            start = end
        if "".join(pieces) != text:
            raise ValueError("Tokenizer split did not preserve the source text")
        return tuple(pieces)

    def _token_bytes(self, tokens: Sequence[int]) -> bytes:
        return b"".join(self._encoding.decode_single_token_bytes(token) for token in tokens)
