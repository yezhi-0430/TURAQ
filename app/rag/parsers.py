"""
文档解析器

支持多种文档格式的解析
"""

import os
from typing import Optional
from pathlib import Path
import PyPDF2
import docx


class DocumentParser:
    """文档解析器，支持多种格式"""

    @staticmethod
    def parse(file_path: str) -> str:
        """
        自动识别并解析文档

        Args:
            file_path: 文件路径

        Returns:
            解析后的文本内容

        Raises:
            ValueError: 不支持的文件格式
            FileNotFoundError: 文件不存在
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_ext = Path(file_path).suffix.lower()

        if file_ext == '.pdf':
            return DocumentParser.parse_pdf(file_path)
        elif file_ext == '.txt':
            return DocumentParser.parse_txt(file_path)
        elif file_ext in ['.docx', '.doc']:
            return DocumentParser.parse_docx(file_path)
        elif file_ext == '.md':
            return DocumentParser.parse_txt(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {file_ext}")

    @staticmethod
    def parse_pdf(file_path: str) -> str:
        """
        解析 PDF 文件

        Args:
            file_path: PDF 文件路径

        Returns:
            提取的文本内容
        """
        text = ""
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)

                for page_num in range(num_pages):
                    page = reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"

            # 清理文本
            text = DocumentParser._clean_text(text)
            return text

        except Exception as e:
            raise ValueError(f"PDF 解析失败: {str(e)}")

    @staticmethod
    def parse_txt(file_path: str) -> str:
        """
        解析文本文件

        Args:
            file_path: 文本文件路径

        Returns:
            文本内容
        """
        try:
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']

            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        text = f.read()
                    return DocumentParser._clean_text(text)
                except UnicodeDecodeError:
                    continue

            # 如果所有编码都失败
            raise ValueError("无法识别文件编码")

        except Exception as e:
            raise ValueError(f"文本文件解析失败: {str(e)}")

    @staticmethod
    def parse_docx(file_path: str) -> str:
        """
        解析 Word 文档

        Args:
            file_path: Word 文档路径

        Returns:
            提取的文本内容
        """
        try:
            doc = docx.Document(file_path)
            text = ""

            # 提取段落
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text + "\n\n"

            # 提取表格
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join([cell.text for cell in row.cells])
                    text += row_text + "\n"
                text += "\n"

            return DocumentParser._clean_text(text)

        except Exception as e:
            raise ValueError(f"Word 文档解析失败: {str(e)}")

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        清理文本

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        # 删除多余的空白行
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)

        # 合并成文本，段落之间保留两个换行
        text = '\n\n'.join(cleaned_lines)

        # 删除多余的空格
        text = ' '.join(text.split())

        # 恢复段落分隔
        text = text.replace('\n\n', '\n\n')

        return text

    @staticmethod
    def get_file_info(file_path: str) -> dict:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        file_stat = os.stat(file_path)
        file_path_obj = Path(file_path)

        return {
            'filename': file_path_obj.name,
            'extension': file_path_obj.suffix,
            'size_bytes': file_stat.st_size,
            'size_mb': round(file_stat.st_size / (1024 * 1024), 2),
            'modified_time': file_stat.st_mtime,
        }
