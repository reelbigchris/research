#!/usr/bin/env python3
"""
PySide6 LLM Chat Interface
A modern, minimalist chat interface with streaming support and Markdown rendering.
Uses the Nord color scheme.
"""

import sys
import re
import json
import markdown
import time
from datetime import datetime
from markdown.extensions.codehilite import CodeHiliteExtension
from pygments.formatters import HtmlFormatter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QScrollArea, QLabel, QFrame,
    QDialog, QPlainTextEdit, QToolButton, QSizePolicy, QProgressBar,
    QMenuBar, QMenu, QFileDialog, QTextBrowser
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QElapsedTimer, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QFont, QTextCursor, QClipboard, QIcon
import abc
import random


# Nord Color Scheme
NORD = {
    # Polar Night (dark backgrounds)
    'nord0': '#2E3440',
    'nord1': '#3B4252',
    'nord2': '#434C5E',
    'nord3': '#4C566A',
    # Snow Storm (bright foregrounds)
    'nord4': '#D8DEE9',
    'nord5': '#E5E9F0',
    'nord6': '#ECEFF4',
    # Frost (blues)
    'nord7': '#8FBCBB',
    'nord8': '#88C0D0',
    'nord9': '#81A1C1',
    'nord10': '#5E81AC',
    # Aurora (accents)
    'nord11': '#BF616A',  # Red
    'nord12': '#D08770',  # Orange
    'nord13': '#EBCB8B',  # Yellow
    'nord14': '#A3BE8C',  # Green
    'nord15': '#B48EAD',  # Purple
}


class TokenCounter:
    """Simple token counter for estimating token usage."""

    @staticmethod
    def estimate_tokens(text):
        """
        Estimate token count using a simple heuristic.
        Roughly 1 token per 4 characters for English text.
        This is an approximation; real tokenizers are more complex.
        """
        if not text:
            return 0

        # Simple estimation: ~4 chars per token
        # This is approximate but good enough for UI feedback
        char_count = len(text)
        word_count = len(text.split())

        # Use average of character-based and word-based estimates
        char_estimate = char_count / 4
        word_estimate = word_count * 1.3  # ~1.3 tokens per word on average

        return int((char_estimate + word_estimate) / 2)

    @staticmethod
    def format_token_count(count, max_tokens=None):
        """Format token count for display."""
        if max_tokens:
            percentage = (count / max_tokens) * 100
            return f"{count:,} / {max_tokens:,} tokens ({percentage:.1f}%)"
        return f"{count:,} tokens"


class MarkdownRenderer:
    """Robust Markdown renderer with syntax highlighting that handles errors gracefully."""

    def __init__(self):
        # Configure CodeHilite extension with Nord-themed colors
        self.md = markdown.Markdown(
            extensions=[
                CodeHiliteExtension(
                    linenums=False,
                    css_class='highlight',
                    guess_lang=True
                ),
                'fenced_code',
                'tables',
                'nl2br'
            ]
        )

        # Generate Nord-themed Pygments CSS
        self.pygments_css = self._generate_nord_pygments_css()

    def _generate_nord_pygments_css(self):
        """Generate Nord-themed CSS for Pygments syntax highlighting."""
        return f"""
            /* Pygments Nord Theme for Code Highlighting */
            .highlight .hll {{ background-color: {NORD['nord2']} }}  /* Line highlight */

            /* Syntax highlighting colors */
            .highlight .hll {{ background-color: {NORD['nord2']} }}  /* Line highlight */
            .highlight .c {{ color: {NORD['nord3']}; font-style: italic }}  /* Comment */
            .highlight .err {{ color: {NORD['nord11']}; }}  /* Error */
            .highlight .k {{ color: {NORD['nord9']}; font-weight: bold }}  /* Keyword */
            .highlight .o {{ color: {NORD['nord9']} }}  /* Operator */
            .highlight .cm {{ color: {NORD['nord3']}; font-style: italic }}  /* Comment.Multiline */
            .highlight .cp {{ color: {NORD['nord9']} }}  /* Comment.Preproc */
            .highlight .c1 {{ color: {NORD['nord3']}; font-style: italic }}  /* Comment.Single */
            .highlight .cs {{ color: {NORD['nord3']}; font-style: italic }}  /* Comment.Special */

            .highlight .gd {{ color: {NORD['nord11']} }}  /* Generic.Deleted */
            .highlight .ge {{ font-style: italic }}  /* Generic.Emph */
            .highlight .gr {{ color: {NORD['nord11']} }}  /* Generic.Error */
            .highlight .gh {{ color: {NORD['nord8']}; font-weight: bold }}  /* Generic.Heading */
            .highlight .gi {{ color: {NORD['nord14']} }}  /* Generic.Inserted */
            .highlight .go {{ color: {NORD['nord4']} }}  /* Generic.Output */
            .highlight .gp {{ color: {NORD['nord4']} }}  /* Generic.Prompt */
            .highlight .gs {{ font-weight: bold }}  /* Generic.Strong */
            .highlight .gu {{ color: {NORD['nord8']}; font-weight: bold }}  /* Generic.Subheading */
            .highlight .gt {{ color: {NORD['nord11']} }}  /* Generic.Traceback */

            .highlight .kc {{ color: {NORD['nord9']}; font-weight: bold }}  /* Keyword.Constant */
            .highlight .kd {{ color: {NORD['nord9']}; font-weight: bold }}  /* Keyword.Declaration */
            .highlight .kn {{ color: {NORD['nord9']}; font-weight: bold }}  /* Keyword.Namespace */
            .highlight .kp {{ color: {NORD['nord9']}; font-weight: bold }}  /* Keyword.Pseudo */
            .highlight .kr {{ color: {NORD['nord9']}; font-weight: bold }}  /* Keyword.Reserved */
            .highlight .kt {{ color: {NORD['nord9']}; font-weight: bold }}  /* Keyword.Type */

            .highlight .m {{ color: {NORD['nord15']} }}  /* Literal.Number */
            .highlight .s {{ color: {NORD['nord14']} }}  /* Literal.String */

            .highlight .na {{ color: {NORD['nord8']} }}  /* Name.Attribute */
            .highlight .nb {{ color: {NORD['nord8']} }}  /* Name.Builtin */
            .highlight .nc {{ color: {NORD['nord7']} }}  /* Name.Class */
            .highlight .no {{ color: {NORD['nord15']} }}  /* Name.Constant */
            .highlight .nd {{ color: {NORD['nord10']} }}  /* Name.Decorator */
            .highlight .ni {{ color: {NORD['nord7']} }}  /* Name.Entity */
            .highlight .ne {{ color: {NORD['nord11']} }}  /* Name.Exception */
            .highlight .nf {{ color: {NORD['nord8']} }}  /* Name.Function */
            .highlight .nl {{ color: {NORD['nord7']} }}  /* Name.Label */
            .highlight .nn {{ color: {NORD['nord7']} }}  /* Name.Namespace */
            .highlight .nt {{ color: {NORD['nord9']} }}  /* Name.Tag */
            .highlight .nv {{ color: {NORD['nord4']} }}  /* Name.Variable */
            .highlight .nx {{ color: {NORD['nord4']} }}  /* Name.Other */

            .highlight .ow {{ color: {NORD['nord9']}; font-weight: bold }}  /* Operator.Word */
            .highlight .w {{ color: {NORD['nord4']} }}  /* Text.Whitespace */

            .highlight .mb {{ color: {NORD['nord15']} }}  /* Literal.Number.Bin */
            .highlight .mf {{ color: {NORD['nord15']} }}  /* Literal.Number.Float */
            .highlight .mh {{ color: {NORD['nord15']} }}  /* Literal.Number.Hex */
            .highlight .mi {{ color: {NORD['nord15']} }}  /* Literal.Number.Integer */
            .highlight .mo {{ color: {NORD['nord15']} }}  /* Literal.Number.Oct */

            .highlight .sa {{ color: {NORD['nord14']} }}  /* Literal.String.Affix */
            .highlight .sb {{ color: {NORD['nord14']} }}  /* Literal.String.Backtick */
            .highlight .sc {{ color: {NORD['nord14']} }}  /* Literal.String.Char */
            .highlight .dl {{ color: {NORD['nord14']} }}  /* Literal.String.Delimiter */
            .highlight .sd {{ color: {NORD['nord3']}; font-style: italic }}  /* Literal.String.Doc */
            .highlight .s2 {{ color: {NORD['nord14']} }}  /* Literal.String.Double */
            .highlight .se {{ color: {NORD['nord13']} }}  /* Literal.String.Escape */
            .highlight .sh {{ color: {NORD['nord14']} }}  /* Literal.String.Heredoc */
            .highlight .si {{ color: {NORD['nord13']} }}  /* Literal.String.Interpol */
            .highlight .sx {{ color: {NORD['nord14']} }}  /* Literal.String.Other */
            .highlight .sr {{ color: {NORD['nord13']} }}  /* Literal.String.Regex */
            .highlight .s1 {{ color: {NORD['nord14']} }}  /* Literal.String.Single */
            .highlight .ss {{ color: {NORD['nord7']} }}  /* Literal.String.Symbol */

            .highlight .bp {{ color: {NORD['nord8']} }}  /* Name.Builtin.Pseudo */
            .highlight .fm {{ color: {NORD['nord8']} }}  /* Name.Function.Magic */
            .highlight .vc {{ color: {NORD['nord4']} }}  /* Name.Variable.Class */
            .highlight .vg {{ color: {NORD['nord4']} }}  /* Name.Variable.Global */
            .highlight .vi {{ color: {NORD['nord4']} }}  /* Name.Variable.Instance */
            .highlight .vm {{ color: {NORD['nord4']} }}  /* Name.Variable.Magic */

            .highlight .il {{ color: {NORD['nord15']} }}  /* Literal.Number.Integer.Long */
        """

    def render(self, text):
        """Render markdown to HTML with syntax highlighting, handling errors gracefully."""
        try:
            # Reset the markdown parser
            self.md.reset()
            html = self.md.convert(text)
            
            # Post-process HTML: Wrap code blocks in a custom table with a "Copy" header
            # We look for the div class="highlight" usually generated by Pygments
            pattern = re.compile(r'<div class="highlight">(.*?)</div>', re.DOTALL)
            
            def replace_block(match):
                content = match.group(1).strip()
                # Remove potential trailing newlines/whitespace before closing tags
                # This prevents the "extra blank line" look in the code block
                content = re.sub(r'[\s\n\r]+</pre>', '</pre>', content)
                content = re.sub(r'[\s\n\r]+</code>', '</code>', content)
                
                return (
                    f'<table class="highlight" width="100%" bgcolor="#232730" border="0" cellpadding="0" cellspacing="0" style="border-radius: 6px; margin: 10px 0; border: 2px solid {NORD["nord3"]}; border-collapse: separate; border-spacing: 0;">'
                    f'<tr><td style="padding: 12px; border: none;">{content}</td></tr></table>'
                )

            html = pattern.sub(replace_block, html)

            # Also handle bare pre tags (fallback)
            if '<pre>' in html and '<table' not in html:
                 # Simple fallback without copy button for now, or could add it too
                 html = html.replace('<pre>', 
                    f'<table width="100%" bgcolor="#2E3440" border="0" cellpadding="12" style="border-radius: 6px; margin: 10px 0;"><tr><td><pre style="margin:0;">')
                 html = html.replace('</pre>', '</pre></td></tr></table>')

            # Apply Nord-themed styling
             # Note: We return code_blocks alongside the HTML
            styled_html = f"""
            <style>
                body {{
                    color: {NORD['nord4']};
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                }}
                code {{
                    background-color: transparent;
                    color: {NORD['nord14']};
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
                    font-size: 13px;
                }}
                pre {{
                    background-color: transparent;
                    border: none;
                    border-radius: 0;
                    padding: 0;
                    margin: 0;
                    overflow-x: auto;
                }}
                pre code {{
                    background-color: transparent;
                    padding: 0;
                }}
                blockquote {{
                    border-left: 3px solid {NORD['nord10']};
                    padding-left: 12px;
                    margin-left: 0;
                    color: {NORD['nord4']};
                    opacity: 0.9;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 10px 0;
                }}
                /* Ensure our highlight table doesn't get messed up by global table styles */
                table.highlight td {{
                    border: none;
                    padding: 0;
                }}
                th, td {{
                    border: 1px solid {NORD['nord3']};
                    padding: 8px;
                    text-align: left;
                }}
                /* Remove border from highlight table cells specifically */
                table.highlight td {{
                    border: none;
                }}
                th {{
                    background-color: {NORD['nord1']};
                    font-weight: 600;
                }}
                a {{
                    color: {NORD['nord8']};
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: {NORD['nord6']};
                    margin-top: 16px;
                    margin-bottom: 8px;
                }}
                ul, ol {{
                    padding-left: 24px;
                }}
                li {{
                    margin-bottom: 6px;
                }}

                {self.pygments_css}
            </style>
            {html}
            """
            return styled_html, []
        except Exception as e:
            # If markdown rendering fails, return escaped text
            print(f"Markdown rendering error: {e}")
            return f"<pre>{text}</pre>", []
            escaped_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f"<pre>{escaped_text}</pre>"


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers."""

    @abc.abstractmethod
    def stream_response(self, user_text):
        """
        Stream a response from the LLM.
        Should yielding tokens (or words).
        """
        pass

    @abc.abstractmethod
    def generate_thinking(self, user_text):
        """Generate thinking text for the response."""
        pass


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self):
        self.responses = [
            """Thank you for your message! I'm a **mock LLM** response demonstrating the streaming capabilities and **syntax highlighting** of this interface.

```python
# Python with Nord-themed syntax highlighting
def process_message(text: str) -> dict:
    '''Process user message and return response.'''
    return {'status': 'success', 'message': f"Processed: {text}"}
```

The interface handles markdown gracefully!""",
            """Interesting! Let me respond with some **syntax-highlighted examples**!

## Key Points:
- This interface uses the **Nord color scheme** throughout
- Messages stream in word by word with smooth animations

> "Good code is its own best documentation." - Steve McConnell

```typescript
async function sendMessage(msg: string): Promise<Response> {
    return await fetch('/api/chat', { method: 'POST', body: JSON.stringify({ msg }) });
}
```""",
            """Got your message! Let me show you **syntax highlighting across multiple languages**.

### Shell Script:
```bash
#!/bin/bash
echo "Starting deployment..."
docker-compose up -d
```

### C++:
```cpp
#include <iostream>
int main() {
    std::cout << "Hello, PySide6!" << std::endl;
    return 0;
}
```"""
        ]
        self.thinking_options = [
            "Analyzing the user's query and preparing a helpful response...",
            "Thinking about how to best explain these concepts using code examples...",
            "Processing the technical request and structuring the markdown response...",
            "Considering the best programming language for the demonstration...",
        ]

    def stream_response(self, user_text):
        response = random.choice(self.responses)
        # Yield words with a small delay simulation is handled by the worker
        for word in response.split(' '):
            yield word

    def generate_thinking(self, user_text):
        return random.choice(self.thinking_options)


class AnthropicProvider(LLMProvider):
    """Real Anthropic LLM provider (requires anthropic library)."""

    def __init__(self, api_key, model="claude-3-7-sonnet-latest"):
        self.api_key = api_key
        self.model = model
        # Note: In a real implementation, you would initialize the client here
        # self.client = anthropic.Anthropic(api_key=api_key)

    def stream_response(self, user_text):
        """
        Example implementation for Anthropic streaming.
        This is a placeholder demonstrating the expected structure.
        """
        # with self.client.messages.stream(...) as stream:
        #     for event in stream:
        #         if event.type == "content_block_delta":
        #             yield event.delta.text
        
        # For now, falls back to mock for demo
        mock = MockProvider()
        return mock.stream_response(user_text)

    def generate_thinking(self, user_text):
        """Anthropic models often provide a thinking process."""
        return "I am analyzing your request using my internal reasoning chain..."


class WorkerSignals(QObject):
    """Signals for the streaming worker."""
    token = Signal(str)
    thinking = Signal(str)
    finished = Signal()
    error = Signal(str)


class StreamingWorker(QRunnable):
    """Worker for streaming LLM responses in a background thread."""

    def __init__(self, provider, user_text):
        super().__init__()
        self.provider = provider
        self.user_text = user_text
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def cancel(self):
        """Cancel the streaming process."""
        self._is_cancelled = True

    def run(self):
        """Execute the streaming logic."""
        try:
            # 1. Generate Thinking
            if self._is_cancelled:
                return
            thinking = self.provider.generate_thinking(self.user_text)
            self.signals.thinking.emit(thinking)

            # Optional: Simulate network latency/thinking time
            time.sleep(0.5)

            # 2. Stream Response
            for i, token in enumerate(self.provider.stream_response(self.user_text)):
                if self._is_cancelled:
                    break

                # Add space if not the first token (simple word-based mock)
                if i > 0:
                    self.signals.token.emit(" " + token)
                else:
                    self.signals.token.emit(token)

                # Simulate streaming delay (e.g., 50ms per word)
                time.sleep(0.05)

            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))


class MessageWidget(QFrame):
    """Widget representing a single chat message."""

    copy_requested = Signal(str)
    regenerate_requested = Signal()

    def __init__(self, text, is_user=True, thinking_text="", parent=None):
        super().__init__(parent)
        self.text = text
        self.is_user = is_user
        self.original_text = text
        self.thinking_text = thinking_text
        self.renderer = MarkdownRenderer()
        self.is_streaming = False
        self.timestamp = datetime.now()
        self.response_time = None
        self.start_time = None
        
        # Debouncing markdown rendering
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._do_render)
        
        self.code_blocks = [] # Store extracted code blocks for copying
        self.thinking_expanded = False # Initialize expanded state

        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        """Set up the message widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # Header with role label, timestamp, and metrics
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        # Role label with emoji
        role = "⚽ You" if self.is_user else "🦊 Assistant"
        self.role_label = QLabel(role)
        self.role_label.setFont(QFont("SF Pro", 11, QFont.Bold))
        self.role_label.setStyleSheet(f"color: {NORD['nord6']};")  # Brighter text
        header_layout.addWidget(self.role_label)

        # Timestamp
        time_str = self.timestamp.strftime("%H:%M:%S")
        self.timestamp_label = QLabel(time_str)
        self.timestamp_label.setFont(QFont("SF Pro", 10))
        self.timestamp_label.setStyleSheet(f"color: {NORD['nord4']};")  # Brighter gray
        header_layout.addWidget(self.timestamp_label)

        # Response time and token count (for assistant messages)
        if not self.is_user:
            self.metrics_label = QLabel("")
            self.metrics_label.setFont(QFont("SF Pro", 10))
            self.metrics_label.setStyleSheet(f"color: {NORD['nord4']};")  # Brighter gray
            self.metrics_label.hide()  # Show after streaming completes
            header_layout.addWidget(self.metrics_label)

        # Waiting indicator (for assistant messages only)
        if not self.is_user:
            self.waiting_label = QLabel("Thinking")
            self.waiting_label.setFont(QFont("SF Pro", 10))
            self.waiting_label.setStyleSheet(f"color: {NORD['nord13']};")  # Yellow
            self.waiting_label.hide()
            header_layout.addWidget(self.waiting_label)

        header_layout.addStretch()

        # Action buttons for assistant messages
        if not self.is_user:
            self.view_original_btn = QToolButton()
            self.view_original_btn.setText("View Original")
            self.view_original_btn.clicked.connect(self.show_original)
            self.view_original_btn.setCursor(Qt.PointingHandCursor)
            header_layout.addWidget(self.view_original_btn)

            self.regenerate_btn = QToolButton()
            self.regenerate_btn.setText("Regenerate")
            self.regenerate_btn.clicked.connect(self.regenerate_requested.emit)
            self.regenerate_btn.setCursor(Qt.PointingHandCursor)
            header_layout.addWidget(self.regenerate_btn)

        # Copy button
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.clicked.connect(self.copy_message)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        header_layout.addWidget(self.copy_btn)

        layout.addLayout(header_layout)

        # Thinking box (expandable, for assistant messages only)
        if not self.is_user and self.thinking_text:
            self.thinking_frame = QFrame()
            self.thinking_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {NORD['nord0']};
                    border: 1px solid {NORD['nord3']};
                    border-radius: 4px;
                }}
            """)
            thinking_layout = QVBoxLayout(self.thinking_frame)
            thinking_layout.setContentsMargins(8, 6, 8, 6)
            thinking_layout.setSpacing(4)

            # Thinking header (clickable to expand/collapse)
            thinking_header = QHBoxLayout()
            self.thinking_toggle_btn = QToolButton()
            self.thinking_toggle_btn.setText("▶ View Thinking")
            self.thinking_toggle_btn.setStyleSheet(f"""
                QToolButton {{
                    background: transparent;
                    color: {NORD['nord13']};
                    border: none;
                    text-align: left;
                    font-weight: bold;
                    font-size: 11px;
                }}
                QToolButton:hover {{
                    color: {NORD['nord12']};
                }}
            """)
            self.thinking_toggle_btn.clicked.connect(self.toggle_thinking)
            self.thinking_toggle_btn.setCursor(Qt.PointingHandCursor)
            thinking_header.addWidget(self.thinking_toggle_btn)
            thinking_header.addStretch()
            thinking_layout.addLayout(thinking_header)

            # Thinking content (initially hidden)
            self.thinking_content = QTextEdit()
            self.thinking_content.setReadOnly(True)
            self.thinking_content.setFrameStyle(QFrame.NoFrame)
            self.thinking_content.setStyleSheet(f"""
                QTextEdit {{
                    background-color: transparent;
                    color: {NORD['nord4']};
                    font-style: italic;
                }}
            """)
            escaped_thinking = self.thinking_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            self.thinking_content.setHtml(f"<div style='color: {NORD['nord4']}; font-style: italic;'>{escaped_thinking}</div>")
            self.thinking_content.hide()
            thinking_layout.addWidget(self.thinking_content)

            self.thinking_expanded = False
            layout.addWidget(self.thinking_frame)
        else:
            self.thinking_frame = None

        # Message content
        self.content_display = QTextBrowser()
        self.content_display.setOpenLinks(False)
        self.content_display.anchorClicked.connect(self.handle_link_click)
        self.content_display.setReadOnly(True)
        self.content_display.setFrameStyle(QFrame.NoFrame)
        self.content_display.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout.addWidget(self.content_display)

        # Update content and adjust height
        # We do this after adding to layout so Qt can calculate sizes properly
        self.update_content()

    def resizeEvent(self, event):
        """Handle resize events to adjust text wrapping."""
        super().resizeEvent(event)
        self.adjust_height()

    def _update_text_edit_height(self, text_edit):
        """Update height of a text edit based on its content and viewport width."""
        if not text_edit:
            return 0
            
        # Ensure text wraps at the current viewport width
        viewport_width = text_edit.viewport().width()
        if viewport_width > 0:
            text_edit.document().setTextWidth(viewport_width)
            
        # Get height and set it
        doc_height = text_edit.document().size().height()
        text_edit.setFixedHeight(int(doc_height + 10))
        return doc_height

    def toggle_thinking(self):
        """Toggle the thinking box visibility."""
        self.thinking_expanded = not self.thinking_expanded
        if self.thinking_expanded:
            self.thinking_toggle_btn.setText("▼ Hide Thinking")
            self.thinking_content.show()
            # Adjust height for thinking content
            self._update_text_edit_height(self.thinking_content)
        else:
            self.thinking_toggle_btn.setText("▶ View Thinking")
            self.thinking_content.hide()
        self.adjust_height()

    def set_thinking(self, thinking_text):
        """Update the thinking text (useful for streaming thinking)."""
        self.thinking_text = thinking_text
        if not self.thinking_frame:
            # Lazy initialize thinking frame if it didn't exist
            self._create_thinking_frame()
        
        escaped_thinking = self.thinking_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        self.thinking_content.setHtml(f"<div style='color: {NORD['nord4']}; font-style: italic;'>{escaped_thinking}</div>")
        if self.thinking_expanded:
            self._update_text_edit_height(self.thinking_content)

    def _create_thinking_frame(self):
        """Helper to create the thinking frame if it's missing."""
        self.thinking_frame = QFrame()
        self.thinking_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {NORD['nord0']};
                border: 1px solid {NORD['nord3']};
                border-radius: 4px;
            }}
        """)
        thinking_layout = QVBoxLayout(self.thinking_frame)
        thinking_layout.setContentsMargins(8, 6, 8, 6)
        thinking_layout.setSpacing(4)

        # Thinking header
        thinking_header = QHBoxLayout()
        self.thinking_toggle_btn = QToolButton()
        self.thinking_toggle_btn.setText("▶ View Thinking")
        self.thinking_toggle_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {NORD['nord13']};
                border: none;
                text-align: left;
                font-weight: bold;
                font-size: 11px;
            }}
            QToolButton:hover {{
                color: {NORD['nord12']};
            }}
        """)
        self.thinking_toggle_btn.clicked.connect(self.toggle_thinking)
        self.thinking_toggle_btn.setCursor(Qt.PointingHandCursor)
        thinking_header.addWidget(self.thinking_toggle_btn)
        thinking_header.addStretch()
        thinking_layout.addLayout(thinking_header)

        # Thinking content
        self.thinking_content = QTextEdit()
        self.thinking_content.setReadOnly(True)
        self.thinking_content.setFrameStyle(QFrame.NoFrame)
        self.thinking_content.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                color: {NORD['nord4']};
                font-style: italic;
            }}
        """)
        self.thinking_content.hide()
        thinking_layout.addWidget(self.thinking_content)

        self.thinking_expanded = False
        
        # Insert before content_display in the main layout
        self.layout().insertWidget(1, self.thinking_frame)

    def update_content(self, immediate=False):
        """
        Update the message content display.
        Uses debouncing for assistant messages unless immediate=True.
        """
        if self.is_user or immediate or not self.is_streaming:
            self._do_render()
        else:
            if not self.render_timer.isActive():
                self.render_timer.start(100)  # Render every 100ms during streaming

    def _do_render(self):
        """Actual rendering logic."""
        if self.is_user:
            escaped_text = self.text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            html = f"<div style='color: {NORD['nord4']}; white-space: pre-wrap;'>{escaped_text}</div>"
            self.code_blocks = []
        else:
            html, self.code_blocks = self.renderer.render(self.text)

        self.content_display.setHtml(html)
        self._update_text_edit_height(self.content_display)
        self.adjust_height()
        
    def handle_link_click(self, url):
        """Handle execution of code block copy links."""
        # Handle normal links (open in browser)
        import webbrowser
        webbrowser.open(url.toString())

    def adjust_height(self):
        """Adjust widget height to fit content accurately."""
        self._update_text_edit_height(self.content_display)
        if self.thinking_expanded and self.thinking_frame:
             # Ensure thinking content is also updated if expanded
             self._update_text_edit_height(self.thinking_content)
        
        doc_height = self.content_display.document().size().height()
        
        thinking_height = 0
        if self.thinking_frame and self.thinking_expanded:
            thinking_height = self.thinking_frame.height()
        elif self.thinking_frame:
            thinking_height = 36 # Approx closed height (header + padding)
            
        # Header + content + thinking + padding
        # Header is approx 30-40px. 
        # Content height is doc_height.
        # Thinking is variable.
        # Margins are 20 total vertical. 
        # Spacing is 12.
        
        total_height = doc_height + thinking_height + 80 # Adjusted padding estimation
        
        self.setFixedHeight(int(total_height))

    def apply_styles(self):
        """Apply Nord-themed styles to the widget."""
        bg_color = NORD['nord1'] if self.is_user else NORD['nord2']
        border_color = NORD['nord3']
        # Left border color: light blue for user, orange for assistant
        left_border_color = NORD['nord8'] if self.is_user else NORD['nord12']

        self.setStyleSheet(f"""
            MessageWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-left: 4px solid {left_border_color};
                border-radius: 8px;
            }}
            QLabel {{
                color: {NORD['nord6']};
                background: transparent;
            }}
            QToolButton {{
                background-color: {NORD['nord3']};
                color: {NORD['nord4']};
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QToolButton:hover {{
                background-color: {NORD['nord10']};
                color: {NORD['nord6']};
            }}
            QTextEdit {{
                background-color: transparent;
                color: {NORD['nord4']};
                border: none;
            }}
        """)

        # Update content display background
        self.content_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                color: {NORD['nord4']};
            }}
        """)

    def copy_message(self):
        """Copy this message to clipboard."""
        self.copy_requested.emit(self.text)

    def show_original(self):
        """Show the original markdown text."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Original Message")
        dialog.resize(600, 400)

        layout = QVBoxLayout(dialog)

        text_edit = QPlainTextEdit()
        text_edit.setPlainText(self.original_text)
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {NORD['nord0']};
                color: {NORD['nord4']};
                border: 1px solid {NORD['nord3']};
                border-radius: 4px;
                padding: 8px;
                font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            }}
        """)
        layout.addWidget(text_edit)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NORD['nord10']};
                color: {NORD['nord6']};
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {NORD['nord9']};
            }}
        """)
        layout.addWidget(close_btn)

        dialog.exec()

    def start_streaming(self):
        """Start streaming mode with waiting indicator."""
        self.is_streaming = True
        self.start_time = time.time()
        if not self.is_user:
            self.waiting_label.show()
            self.animate_waiting()

    def stop_streaming(self):
        """Stop streaming mode and show metrics."""
        self.is_streaming = False
        if not self.is_user:
            self.waiting_label.hide()

            # Calculate response time
            if self.start_time:
                self.response_time = time.time() - self.start_time

                # Calculate token count
                token_count = TokenCounter.estimate_tokens(self.text)

                # Calculate tokens per second
                tokens_per_sec = token_count / self.response_time if self.response_time > 0 else 0

                # Update metrics label
                metrics_text = f"⏱ {self.response_time:.2f}s | 🔤 {token_count} tokens | ⚡ {tokens_per_sec:.1f} tok/s"
                self.metrics_label.setText(metrics_text)
                self.metrics_label.show()

    def animate_waiting(self):
        """Animate the waiting indicator with a more sophisticated animation."""
        if self.is_streaming and not self.is_user:
            current = self.waiting_label.text()
            # Cycle through different states
            states = ["Thinking", "Thinking.", "Thinking..", "Thinking..."]
            try:
                current_index = states.index(current)
                next_index = (current_index + 1) % len(states)
                self.waiting_label.setText(states[next_index])
            except ValueError:
                self.waiting_label.setText(states[0])

            QTimer.singleShot(400, self.animate_waiting)

    def append_text(self, text):
        """Append text to the message (for streaming)."""
        self.text += text
        self.original_text = self.text
        self.update_content()


class ChatArea(QWidget):
    """Scrollable chat area containing all messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []
        self.setup_ui()

    def setup_ui(self):
        """Set up the chat area UI."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(12)
        self.layout.addStretch()

    def add_message(self, text, is_user=True, thinking_text=""):
        """Add a message to the chat area."""
        message = MessageWidget(text, is_user, thinking_text, self)
        message.copy_requested.connect(self.copy_to_clipboard)

        # Insert before the stretch
        self.layout.insertWidget(self.layout.count() - 1, message)
        self.messages.append(message)

        # Force layout update to ensure proper sizing
        # Need a longer delay to let Qt finish laying out the complex markdown/HTML
        QTimer.singleShot(100, lambda: message.adjust_height())

        return message

    def copy_to_clipboard(self, text):
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)


class InputArea(QWidget):
    """Multi-line input area for user messages with token counter."""

    send_message = Signal(str)
    stop_requested = Signal()

    def __init__(self, max_tokens=4096, parent=None):
        super().__init__(parent)
        self.max_tokens = max_tokens
        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        """Set up the input area UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # Token counter
        info_layout = QHBoxLayout()
        info_layout.setSpacing(8)

        self.token_label = QLabel("0 tokens")
        self.token_label.setFont(QFont("SF Pro", 10))
        self.token_label.setStyleSheet(f"color: {NORD['nord3']};")
        info_layout.addWidget(self.token_label)

        info_layout.addStretch()

        main_layout.addLayout(info_layout)

        # Input area layout
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        # Multi-line text input
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Type your message here... (Ctrl+Enter to send)")
        self.text_input.setMaximumHeight(120)
        # Start with single line height
        self.text_input.setFixedHeight(40)
        self.text_input.installEventFilter(self)
        self.text_input.textChanged.connect(self.update_token_count)
        self.text_input.textChanged.connect(self.adjust_input_height)
        input_layout.addWidget(self.text_input)

        # Send button
        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(60, 40)
        self.send_btn.clicked.connect(self.send)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        input_layout.addWidget(self.send_btn)

        # Stop button (initially hidden)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedSize(60, 40)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NORD['nord11']};
                color: {NORD['nord6']};
            }}
            QPushButton:hover {{
                background-color: #D6707B;
            }}
        """)
        self.stop_btn.hide()
        input_layout.addWidget(self.stop_btn)

        main_layout.addLayout(input_layout)

    def update_token_count(self):
        """Update the token count label as user types."""
        text = self.text_input.toPlainText()
        token_count = TokenCounter.estimate_tokens(text)

        # Update token label
        self.token_label.setText(f"{token_count} tokens")

        # Color code based on usage
        if token_count > self.max_tokens * 0.9:
            self.token_label.setStyleSheet(f"color: {NORD['nord11']};")  # Red
        elif token_count > self.max_tokens * 0.7:
            self.token_label.setStyleSheet(f"color: {NORD['nord13']};")  # Yellow
        else:
            self.token_label.setStyleSheet(f"color: {NORD['nord14']};")  # Green

    def adjust_input_height(self):
        """Dynamically adjust input height based on content."""
        doc_height = self.text_input.document().size().height()
        # Add padding and margin
        new_height = int(doc_height + 16)

        # Clamp between minimum (single line) and maximum height
        new_height = max(40, min(new_height, 120))

        self.text_input.setFixedHeight(new_height)
        # Adjust send button height to match
        self.send_btn.setFixedHeight(new_height)

    def apply_styles(self):
        """Apply Nord-themed styles."""
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {NORD['nord1']};
                color: {NORD['nord4']};
                border: 2px solid {NORD['nord3']};
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }}
            QTextEdit:focus {{
                border-color: {NORD['nord8']};
            }}
            QPushButton {{
                background-color: {NORD['nord10']};
                color: {NORD['nord6']};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {NORD['nord9']};
            }}
            QPushButton:pressed {{
                background-color: {NORD['nord8']};
            }}
        """)

    def eventFilter(self, obj, event):
        """Handle keyboard shortcuts."""
        if obj == self.text_input and event.type() == event.Type.KeyPress:
            # Ctrl+Enter to send
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self.send()
                return True
        return super().eventFilter(obj, event)

    def send(self):
        """Send the message."""
        text = self.text_input.toPlainText().strip()
        if text:
            self.send_message.emit(text)
            self.text_input.clear()
            # Reset height after clearing
            self.text_input.setFixedHeight(40)
            self.send_btn.setFixedHeight(40)

    def set_enabled(self, enabled):
        """Enable or disable input."""
        self.text_input.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)

    def set_streaming_mode(self, is_streaming):
        """Toggle between Send and Stop buttons."""
        if is_streaming:
            self.send_btn.hide()
            self.stop_btn.show()
            self.text_input.setPlaceholderText("Streaming response... Click Stop to cancel.")
        else:
            self.send_btn.show()
            self.stop_btn.hide()
            self.text_input.setPlaceholderText("Type your message here... (Ctrl+Enter to send)")
            self.text_input.setEnabled(True)
            self.send_btn.setEnabled(True)


class StatusBar(QWidget):
    """Status bar showing model info, context usage, and available tools."""

    def __init__(self, model_name="Claude Opus 4.5", max_tokens=4096, parent=None):
        super().__init__(parent)
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        """Set up the status bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(16)

        # Model indicator
        model_icon = QLabel("🤖")
        model_icon.setFont(QFont("SF Pro", 12))
        layout.addWidget(model_icon)

        self.model_label = QLabel(self.model_name)
        self.model_label.setFont(QFont("SF Pro", 10, QFont.Bold))
        self.model_label.setStyleSheet(f"color: {NORD['nord8']};")
        layout.addWidget(self.model_label)

        layout.addWidget(self._create_separator())

        # Context usage
        context_icon = QLabel("📊")
        context_icon.setFont(QFont("SF Pro", 12))
        layout.addWidget(context_icon)

        self.context_label = QLabel(f"Context: 0 / {self.max_tokens:,}")
        self.context_label.setFont(QFont("SF Pro", 10))
        self.context_label.setStyleSheet(f"color: {NORD['nord4']};")
        layout.addWidget(self.context_label)

        layout.addWidget(self._create_separator())

        # Available tools
        tools_icon = QLabel("🔧")
        tools_icon.setFont(QFont("SF Pro", 12))
        layout.addWidget(tools_icon)

        self.tools_label = QLabel("Tools:")
        self.tools_label.setFont(QFont("SF Pro", 10))
        self.tools_label.setStyleSheet(f"color: {NORD['nord4']};")
        layout.addWidget(self.tools_label)

        # Mock tool indicators
        self.tool_badges = []

        # Python tool
        python_badge = self._create_tool_badge("Python", True)
        layout.addWidget(python_badge)
        self.tool_badges.append(python_badge)

        # Git tool
        git_badge = self._create_tool_badge("Git", True)
        layout.addWidget(git_badge)
        self.tool_badges.append(git_badge)

        # Docker tool
        docker_badge = self._create_tool_badge("Docker", False)
        layout.addWidget(docker_badge)
        self.tool_badges.append(docker_badge)

        # Bash tool
        bash_badge = self._create_tool_badge("Bash", True)
        layout.addWidget(bash_badge)
        self.tool_badges.append(bash_badge)

        layout.addStretch()

    def _create_separator(self):
        """Create a vertical separator."""
        separator = QLabel("|")
        separator.setStyleSheet(f"color: {NORD['nord3']};")
        separator.setFont(QFont("SF Pro", 10))
        return separator

    def _create_tool_badge(self, name, available):
        """Create a tool availability badge."""
        badge = QLabel(name)
        badge.setFont(QFont("SF Pro", 9))
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {NORD['nord14'] if available else NORD['nord3']};
                color: {NORD['nord0']};
                padding: 2px 6px;
                border-radius: 3px;
                font-weight: bold;
            }}
        """)
        badge.setToolTip(f"{name} is {'available' if available else 'not available'}")
        return badge

    def update_context(self, used_tokens):
        """Update context window indicator."""
        percentage = (used_tokens / self.max_tokens) * 100
        self.context_label.setText(f"Context: {used_tokens:,} / {self.max_tokens:,} ({percentage:.1f}%)")

        # Color code based on context usage
        if percentage > 90:
            self.context_label.setStyleSheet(f"color: {NORD['nord11']};")  # Red
        elif percentage > 70:
            self.context_label.setStyleSheet(f"color: {NORD['nord13']};")  # Yellow
        else:
            self.context_label.setStyleSheet(f"color: {NORD['nord4']};")  # Normal

    def apply_styles(self):
        """Apply Nord-themed styles."""
        self.setStyleSheet(f"""
            StatusBar {{
                background-color: {NORD['nord1']};
                border-top: 1px solid {NORD['nord3']};
            }}
        """)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.provider = MockProvider()
        self.thread_pool = QThreadPool.globalInstance()
        self.current_worker = None
        
        self.setup_ui()
        self.apply_styles()

        # Demo: Add a welcome message
        self.add_welcome_message()

    def setup_ui(self):
        """Set up the main window UI."""
        self.setWindowTitle("LLM Chat Interface")
        self.resize(900, 700)

        # Menu bar
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        export_json_action = file_menu.addAction("Export to JSON...")
        export_json_action.triggered.connect(self.export_to_json)

        file_menu.addSeparator()

        quit_action = file_menu.addAction("Quit")
        quit_action.triggered.connect(self.close)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        copy_all_action = edit_menu.addAction("Copy All Messages")
        copy_all_action.triggered.connect(self.copy_all)

        clear_action = edit_menu.addAction("Clear Chat")
        clear_action.triggered.connect(self.clear_chat)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Scrollable chat area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.chat_area = ChatArea()
        scroll.setWidget(self.chat_area)

        main_layout.addWidget(scroll, stretch=1)

        # Store scroll area for auto-scrolling
        self.scroll_area = scroll

        # Input area
        self.input_area = InputArea()
        self.input_area.send_message.connect(self.handle_user_message)
        self.input_area.stop_requested.connect(self.stop_current_streaming)
        main_layout.addWidget(self.input_area)

        # Status bar
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar)

    def apply_styles(self):
        """Apply Nord-themed styles to the main window."""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {NORD['nord0']};
            }}
            QWidget {{
                background-color: {NORD['nord0']};
                color: {NORD['nord4']};
            }}
            QPushButton {{
                background-color: {NORD['nord3']};
                color: {NORD['nord4']};
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {NORD['nord10']};
                color: {NORD['nord6']};
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {NORD['nord1']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {NORD['nord3']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {NORD['nord10']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

    def add_welcome_message(self):
        """Add a welcome message to the chat."""
        welcome = """# Welcome to the LLM Chat Interface!

This is a **modern, minimalist** chat interface built with PySide6 and styled with the Nord color scheme.

## Core Features:
- 🎨 Beautiful Nord-themed design with carefully chosen colors
- 📝 Robust Markdown rendering with **Pygments syntax highlighting**
- ⚡ Streaming message support with animated indicators
- 📋 Copy individual messages or entire conversations
- ✅ Select multiple messages at once
- 🔄 Regenerate and view original responses
- ⌨️ Keyboard shortcuts (Ctrl+Enter to send)

## Advanced Features (NEW!):
- 🔤 **Real-time token counter** - See estimated tokens as you type
- 📊 **Context window indicator** - Track conversation token usage
- ⏱️ **Response metrics** - Time, token count, and tokens/second for each response
- 💭 **Expandable thinking box** - View the model's reasoning process
- 🕒 **Message timestamps** - Track when each message was sent
- 🎯 **Improved animations** - More realistic "Thinking..." indicator

## Syntax Highlighting Demo

The interface now features full **Pygments-powered syntax highlighting** with Nord-themed colors!

### Python Example:
```python
class MarkdownRenderer:
    def __init__(self):
        self.md = markdown.Markdown(extensions=['codehilite', 'tables'])

    def render(self, text):
        # Render markdown to HTML with syntax highlighting
        try:
            return self.md.convert(text)
        except Exception as e:
            return f"<pre>{text}</pre>"
```

### JavaScript Example:
```javascript
async function fetchLLMResponse(message) {
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
    });
    return await response.json();
}
```

### Rust Example:
```rust
fn main() {
    let numbers = vec![1, 2, 3, 4, 5];
    let sum: i32 = numbers.iter().sum();
    println!("The sum is: {}", sum);
}
```

> **Note**: The syntax highlighter automatically detects the language and applies appropriate Nord-themed colors!

## Markdown Features

| Feature | Support | Description |
|---------|---------|-------------|
| Headers | ✅ | H1 through H6 |
| Code Blocks | ✅ | With syntax highlighting |
| Tables | ✅ | Full GFM tables |
| Lists | ✅ | Ordered and unordered |
| Blockquotes | ✅ | Nested quotes supported |
| Links | ✅ | Inline and reference |

Try sending a message with code blocks in different languages to see the highlighting in action!
"""
        # Add welcome message with thinking to demonstrate the feature
        thinking_demo = """Preparing welcome message for new user...
Let me showcase all the key features including:
- Markdown rendering with syntax highlighting
- The new token counter and metrics
- This expandable thinking box itself!
I'll structure this with clear sections and code examples."""
        self.chat_area.add_message(welcome, is_user=False, thinking_text=thinking_demo)

    def handle_user_message(self, text):
        """Handle a user message."""
        # Add user message
        self.chat_area.add_message(text, is_user=True)
        self.scroll_to_bottom(force=True)

        # Update context window
        self.update_context_window()

        # Disable input while processing and show stop button
        self.input_area.set_enabled(False)
        self.input_area.set_streaming_mode(True)

        # Add assistant message placeholder
        assistant_msg = self.chat_area.add_message("", is_user=False)
        assistant_msg.start_streaming()
        self.scroll_to_bottom(force=True)

        # Start background worker
        self.current_worker = StreamingWorker(self.provider, text)
        self.current_worker.signals.thinking.connect(assistant_msg.set_thinking)
        self.current_worker.signals.token.connect(lambda t: self._on_token_received(assistant_msg, t))
        self.current_worker.signals.finished.connect(lambda: self._on_streaming_finished(assistant_msg))
        self.current_worker.signals.error.connect(lambda e: print(f"Streaming Error: {e}"))
        
        self.thread_pool.start(self.current_worker)

    def _on_token_received(self, message_widget, token):
        message_widget.append_text(token)
        self.scroll_to_bottom()

    def _on_streaming_finished(self, message_widget):
        message_widget.stop_streaming()
        self.input_area.set_streaming_mode(False)
        self.update_context_window()
        self.current_worker = None

    def stop_current_streaming(self):
        """Cancel the current streaming worker."""
        if self.current_worker:
            self.current_worker.cancel()
            # The worker's finished signal will call _on_streaming_finished

    def generate_mock_response(self, user_text):
        """Deprecated: generate_mock_response is now handled by MockProvider."""
        pass

    def update_context_window(self):
        """Update context window token count in status bar."""
        total_tokens = 0
        for msg in self.chat_area.messages:
            total_tokens += TokenCounter.estimate_tokens(msg.text)
            if hasattr(msg, 'thinking_text') and msg.thinking_text:
                total_tokens += TokenCounter.estimate_tokens(msg.thinking_text)
        
        self.status_bar.update_context(total_tokens)

    def scroll_to_bottom(self, force=False):
        """
        Scroll chat area to bottom if user is already near the bottom.
        If force=True, scroll regardless of current position.
        Uses QTimer to wait for layout updates.
        """
        scrollbar = self.scroll_area.verticalScrollBar()
        current_value = scrollbar.value()
        max_value = scrollbar.maximum()
        
        # Decide if we should scroll based on current position
        # If force=True or within 100px of bottom
        should_scroll = force or (max_value - current_value < 100)
        
        if should_scroll:
            # We scroll multiple times with small delays to ensure we catch 
            # all layout updates (including the 100ms adjust_height delay)
            QTimer.singleShot(10, lambda: scrollbar.setValue(scrollbar.maximum()))
            QTimer.singleShot(150, lambda: scrollbar.setValue(scrollbar.maximum()))
            QTimer.singleShot(400, lambda: scrollbar.setValue(scrollbar.maximum()))

    def copy_all(self):
        """Copy all messages to clipboard."""
        text = "\n\n---\n\n".join([
            f"{'User' if msg.is_user else 'Assistant'}: {msg.text}"
            for msg in self.chat_area.messages
        ])

        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def export_to_json(self):
        """Export conversation to JSON file."""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Conversation",
            "conversation.json",
            "JSON Files (*.json)"
        )

        if not filename:
            return

        messages = []
        for msg in self.chat_area.messages:
            message_data = {
                "role": "user" if msg.is_user else "assistant",
                "content": msg.text,
                "timestamp": msg.timestamp.isoformat(),
            }

            if not msg.is_user:
                if msg.thinking_text:
                    message_data["thinking"] = msg.thinking_text
                if msg.response_time:
                    message_data["response_time"] = msg.response_time

            messages.append(message_data)

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({"messages": messages}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error exporting to JSON: {e}")

    def clear_chat(self):
        """Clear all messages from the chat."""
        # Remove all messages except the stretch
        for msg in self.chat_area.messages[:]:
            msg.deleteLater()
        self.chat_area.messages.clear()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)

    # Set application-wide font
    font = QFont("SF Pro", 13)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
