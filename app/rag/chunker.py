"""
文本分段器

智能将长文本分割成适合向量化的小块
"""

from typing import List
import re


class TextChunker:
    """文本分段器"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        """
        初始化分段器

        Args:
            chunk_size: 每个块的最大字符数
            overlap: 块之间的重叠字符数，保证上下文连贯
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, strategy: str = 'smart') -> List[str]:
        """
        分割文本

        Args:
            text: 要分割的文本
            strategy: 分割策略
                     - 'simple': 按字符数简单分割
                     - 'paragraph': 按段落分割
                     - 'smart': 智能分割（推荐）

        Returns:
            文本块列表
        """
        if strategy == 'simple':
            return self._chunk_by_chars(text)
        elif strategy == 'paragraph':
            return self._chunk_by_paragraph(text)
        elif strategy == 'smart':
            return self._chunk_smart(text)
        else:
            raise ValueError(f"未知的分割策略: {strategy}")

    def _chunk_by_chars(self, text: str) -> List[str]:
        """
        按字符数简单分割

        Args:
            text: 文本

        Returns:
            文本块列表
        """
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            if chunk.strip():
                chunks.append(chunk.strip())

            start = end - self.overlap

        return chunks

    def _chunk_by_paragraph(self, text: str) -> List[str]:
        """
        按段落分割，保证段落完整性

        Args:
            text: 文本

        Returns:
            文本块列表
        """
        # 按段落分割
        paragraphs = re.split(r'\n\n+', text)
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果当前块加上新段落不超过限制，就合并
            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 保存当前块，开始新块
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para

        # 添加最后一块
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _chunk_smart(self, text: str) -> List[str]:
        """
        智能分割，综合考虑段落、句子和字符数

        Args:
            text: 文本

        Returns:
            文本块列表
        """
        # 先按段落分割
        paragraphs = re.split(r'\n\n+', text)
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 段落本身就很长，需要进一步分割
            if len(para) > self.chunk_size:
                # 保存当前块
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                # 按句子分割长段落
                sentences = self._split_sentences(para)
                temp_chunk = ""

                for sent in sentences:
                    if len(temp_chunk) + len(sent) + 1 <= self.chunk_size:
                        temp_chunk += sent + " "
                    else:
                        if temp_chunk:
                            chunks.append(temp_chunk.strip())
                        temp_chunk = sent + " "

                if temp_chunk:
                    current_chunk = temp_chunk.strip()

            # 段落正常，检查是否能合并
            elif len(current_chunk) + len(para) + 2 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 保存当前块，开始新块
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para

        # 添加最后一块
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """
        分割句子

        Args:
            text: 文本

        Returns:
            句子列表
        """
        # 中文句子分割
        sentences = re.split(r'([。！？\.\!\?]+)', text)
        result = []

        for i in range(0, len(sentences) - 1, 2):
            sent = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')
            if sent.strip():
                result.append(sent.strip())

        return result

    def chunk_with_metadata(self, text: str, source: str = "", strategy: str = 'smart') -> List[dict]:
        """
        分割文本并附加元数据

        Args:
            text: 文本
            source: 来源标识
            strategy: 分割策略

        Returns:
            包含文本和元数据的字典列表
        """
        chunks = self.chunk(text, strategy)

        result = []
        for i, chunk in enumerate(chunks):
            result.append({
                'text': chunk,
                'chunk_index': i,
                'total_chunks': len(chunks),
                'source': source,
                'char_count': len(chunk),
            })

        return result
