"""Licensed converter excerpt from Yui-cx/wechat-article-to-md-skill.
Copyright (c) 2026 Yui-cx. MIT; see vendor/Yui-cx/wechat-article-to-md-skill/LICENSE.
Pinned commit: 41f1ed58a9c74e8c61ffbe8f3290c0d13e5ff759.
Only a comment is translated; the parser algorithm is unchanged.
The host adapter handles body selection, attribution, raw bytes and verified assets.
"""
from __future__ import annotations
import re
from html.parser import HTMLParser
from typing import List, Optional

class HTMLToMarkdownParser(HTMLParser):
    def __init__(self, image_downloader: MarkdownImageDownloader) -> None:
        super().__init__()
        self.image_downloader = image_downloader
        self.result: List[str] = []
        self.tag_stack: List[str] = []
        self.list_stack: List[str] = []
        self.list_counters: List[int] = []
        self.ignore_tags = {'script', 'style', 'nav', 'footer', 'header', 'aside'}
        self.skip_depth = 0
        self.current_href: Optional[str] = None
        self.pending_newlines = 0
        self.in_pre = False

    def add_newlines(self, count: int) -> None:
        self.pending_newlines = max(self.pending_newlines, count)

    def flush_newlines(self) -> None:
        if self.pending_newlines > 0:
            self.result.append('\n' * self.pending_newlines)
            self.pending_newlines = 0

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attrs_dict = {key: value or '' for key, value in attrs}

        if tag in self.ignore_tags:
            self.skip_depth += 1
            return
        if self.skip_depth > 0:
            return

        self.tag_stack.append(tag)
        if tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            self.add_newlines(2)
            self.flush_newlines()
            level = int(tag[1])
            self.result.append('#' * level + ' ')
        elif tag == 'p':
            self.add_newlines(2)
            self.flush_newlines()
        elif tag == 'br':
            self.result.append('  \n')
        elif tag == 'hr':
            self.flush_newlines()
            self.result.append('\n---\n')
        elif tag in {'strong', 'b'}:
            self.result.append('**')
        elif tag in {'em', 'i'}:
            self.result.append('*')
        elif tag == 'code' and not self.in_pre:
            self.result.append('`')
        elif tag == 'pre':
            self.add_newlines(2)
            self.flush_newlines()
            self.result.append('```\n')
            self.in_pre = True
        elif tag == 'blockquote':
            self.add_newlines(2)
            self.flush_newlines()
            self.result.append('> ')
        elif tag == 'a':
            self.current_href = attrs_dict.get('href', '').strip()
            self.result.append('[')
        elif tag == 'img':
            self.flush_newlines()
            source = (
                attrs_dict.get('data-src')
                or attrs_dict.get('data-original')
                or attrs_dict.get('src')
                or ''
            )
            alt_text = attrs_dict.get('alt') or attrs_dict.get('data-alt') or 'image'
            # Register the existing asset reference without downloading again.
            local_name = self.image_downloader.register(source)
            target = local_name or source
            if target:
                self.result.append(f'![{alt_text}]({target})')
                self.add_newlines(2)
        elif tag == 'ul':
            self.add_newlines(2)
            self.flush_newlines()
            self.list_stack.append('ul')
        elif tag == 'ol':
            self.add_newlines(2)
            self.flush_newlines()
            self.list_stack.append('ol')
            self.list_counters.append(1)
        elif tag == 'li':
            self.flush_newlines()
            indent = '  ' * max(0, len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1] == 'ol':
                index = self.list_counters[-1]
                self.result.append(f'{indent}{index}.')
                self.list_counters[-1] += 1
            else:
                self.result.append(f'{indent}- ')
        elif tag == 'table':
            self.add_newlines(2)
            self.flush_newlines()
        elif tag == 'tr':
            self.result.append('|')
        elif tag in {'th', 'td'}:
            self.result.append(' ')

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in self.ignore_tags:
            if self.skip_depth > 0:
                self.skip_depth -= 1
            return
        if self.skip_depth > 0:
            return

        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()

        if tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'blockquote'}:
            self.add_newlines(2)
        elif tag in {'strong', 'b'}:
            self.result.append('**')
        elif tag in {'em', 'i'}:
            self.result.append('*')
        elif tag == 'code' and not self.in_pre:
            self.result.append('`')
        elif tag == 'pre':
            self.result.append('\n```')
            self.add_newlines(2)
            self.in_pre = False
        elif tag == 'a':
            href = (self.current_href or '').strip()
            if href:
                self.result.append(f']({href})')
            else:
                self.result.append(']')
            self.current_href = None
        elif tag == 'ul':
            if self.list_stack:
                self.list_stack.pop()
            self.add_newlines(2)
        elif tag == 'ol':
            if self.list_stack:
                self.list_stack.pop()
            if self.list_counters:
                self.list_counters.pop()
            self.add_newlines(2)
        elif tag == 'li':
            self.add_newlines(1)
        elif tag in {'th', 'td'}:
            self.result.append(' |')
        elif tag == 'tr':
            self.result.append('\n')

    def handle_data(self, data: str) -> None:
        if self.skip_depth > 0:
            return
        self.flush_newlines()
        if self.in_pre:
            self.result.append(data)
            return
        cleaned = re.sub(r'[ \t]+', ' ', data)
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
        if cleaned.strip():
            self.result.append(cleaned)

    def get_markdown(self) -> str:
        content = ''.join(self.result)
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip() + '\n'
