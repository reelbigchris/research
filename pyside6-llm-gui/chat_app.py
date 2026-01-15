#!/usr/bin/env python3
"""
PySide6 LLM Chat Interface
A modern, minimalist chat interface with streaming support and Markdown rendering.
Uses the Nord color scheme.
"""

import sys
import re
import markdown
import time
from datetime import datetime
from markdown.extensions.codehilite import CodeHiliteExtension
from pygments.formatters import HtmlFormatter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QScrollArea, QLabel, QFrame, QCheckBox,
    QDialog, QPlainTextEdit, QToolButton, QSizePolicy, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QElapsedTimer
from PySide6.QtGui import QFont, QTextCursor, QClipboard, QIcon


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
            .highlight {{
                background-color: {NORD['nord0']};
                border-radius: 6px;
            }}
            .highlight pre {{
                margin: 0;
                padding: 12px;
                background-color: {NORD['nord0']};
            }}

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

            # Apply Nord-themed styling
            styled_html = f"""
            <style>
                body {{
                    color: {NORD['nord4']};
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                }}
                code {{
                    background-color: {NORD['nord1']};
                    color: {NORD['nord14']};
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
                    font-size: 13px;
                }}
                pre {{
                    background-color: {NORD['nord1']};
                    border: 1px solid {NORD['nord3']};
                    border-radius: 6px;
                    padding: 12px;
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
                th, td {{
                    border: 1px solid {NORD['nord3']};
                    padding: 8px;
                    text-align: left;
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

                {self.pygments_css}
            </style>
            {html}
            """
            return styled_html
        except Exception as e:
            # If markdown rendering fails, return escaped text
            escaped_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f"<pre>{escaped_text}</pre>"


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
        self.is_selected = False
        self.is_streaming = False
        self.timestamp = datetime.now()
        self.response_time = None  # Will be set when streaming completes
        self.start_time = None

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

        # Selection checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(18, 18)
        self.checkbox.stateChanged.connect(self.on_selection_changed)
        header_layout.addWidget(self.checkbox)

        # Role label
        role = "You" if self.is_user else "Assistant"
        self.role_label = QLabel(role)
        self.role_label.setFont(QFont("SF Pro", 11, QFont.Bold))
        header_layout.addWidget(self.role_label)

        # Timestamp
        time_str = self.timestamp.strftime("%H:%M:%S")
        self.timestamp_label = QLabel(time_str)
        self.timestamp_label.setFont(QFont("SF Pro", 10))
        self.timestamp_label.setStyleSheet(f"color: {NORD['nord3']};")
        header_layout.addWidget(self.timestamp_label)

        # Response time and token count (for assistant messages)
        if not self.is_user:
            self.metrics_label = QLabel("")
            self.metrics_label.setFont(QFont("SF Pro", 10))
            self.metrics_label.setStyleSheet(f"color: {NORD['nord3']};")
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

        # Message content
        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        self.content_display.setFrameStyle(QFrame.NoFrame)
        self.content_display.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Update content
        self.update_content()

        layout.addWidget(self.content_display)

        # Adjust height based on content
        self.adjust_height()

    def toggle_thinking(self):
        """Toggle the thinking box visibility."""
        self.thinking_expanded = not self.thinking_expanded
        if self.thinking_expanded:
            self.thinking_toggle_btn.setText("▼ Hide Thinking")
            self.thinking_content.show()
            # Adjust height for thinking content
            doc_height = self.thinking_content.document().size().height()
            self.thinking_content.setFixedHeight(int(doc_height + 10))
        else:
            self.thinking_toggle_btn.setText("▶ View Thinking")
            self.thinking_content.hide()
        self.adjust_height()

    def update_content(self):
        """Update the message content display."""
        if self.is_user:
            # User messages: simple text with proper escaping
            escaped_text = self.text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            html = f"<div style='color: {NORD['nord4']}; white-space: pre-wrap;'>{escaped_text}</div>"
        else:
            # Assistant messages: render markdown
            html = self.renderer.render(self.text)

        self.content_display.setHtml(html)
        self.adjust_height()

    def adjust_height(self):
        """Adjust widget height to fit content."""
        doc_height = self.content_display.document().size().height()
        self.content_display.setFixedHeight(int(doc_height + 20))

    def apply_styles(self):
        """Apply Nord-themed styles to the widget."""
        bg_color = NORD['nord1'] if self.is_user else NORD['nord2']
        border_color = NORD['nord3']

        self.setStyleSheet(f"""
            MessageWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            MessageWidget[selected="true"] {{
                border: 2px solid {NORD['nord8']};
            }}
            QLabel {{
                color: {NORD['nord6']};
                background: transparent;
            }}
            QCheckBox {{
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 2px solid {NORD['nord3']};
                background-color: {NORD['nord0']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {NORD['nord8']};
                border-color: {NORD['nord8']};
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

    def on_selection_changed(self, state):
        """Handle selection state change."""
        self.is_selected = (state == Qt.Checked)
        self.setProperty("selected", "true" if self.is_selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_selected(self, selected):
        """Set selection state."""
        self.checkbox.setChecked(selected)

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

        return message

    def get_selected_messages(self):
        """Get all selected messages."""
        return [msg for msg in self.messages if msg.is_selected]

    def copy_to_clipboard(self, text):
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)


class InputArea(QWidget):
    """Multi-line input area for user messages with token counter."""

    send_message = Signal(str)

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

        # Token counter and context window indicator
        info_layout = QHBoxLayout()
        info_layout.setSpacing(8)

        self.token_label = QLabel("0 tokens")
        self.token_label.setFont(QFont("SF Pro", 10))
        self.token_label.setStyleSheet(f"color: {NORD['nord3']};")
        info_layout.addWidget(self.token_label)

        info_layout.addStretch()

        self.context_label = QLabel(f"Context: 0 / {self.max_tokens:,}")
        self.context_label.setFont(QFont("SF Pro", 10))
        self.context_label.setStyleSheet(f"color: {NORD['nord3']};")
        info_layout.addWidget(self.context_label)

        main_layout.addLayout(info_layout)

        # Input area layout
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        # Multi-line text input
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Type your message here... (Ctrl+Enter to send)")
        self.text_input.setMaximumHeight(120)
        self.text_input.setMinimumHeight(60)
        self.text_input.installEventFilter(self)
        self.text_input.textChanged.connect(self.update_token_count)
        input_layout.addWidget(self.text_input)

        # Send button
        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(60, 60)
        self.send_btn.clicked.connect(self.send)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        input_layout.addWidget(self.send_btn)

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

    def update_context_window(self, used_tokens):
        """Update context window indicator with conversation token usage."""
        percentage = (used_tokens / self.max_tokens) * 100
        self.context_label.setText(f"Context: {used_tokens:,} / {self.max_tokens:,} ({percentage:.1f}%)")

        # Color code based on context usage
        if percentage > 90:
            self.context_label.setStyleSheet(f"color: {NORD['nord11']};")  # Red
        elif percentage > 70:
            self.context_label.setStyleSheet(f"color: {NORD['nord13']};")  # Yellow
        else:
            self.context_label.setStyleSheet(f"color: {NORD['nord3']};")  # Gray

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

    def set_enabled(self, enabled):
        """Enable or disable input."""
        self.text_input.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.apply_styles()

        # Demo: Add a welcome message
        self.add_welcome_message()

    def setup_ui(self):
        """Set up the main window UI."""
        self.setWindowTitle("LLM Chat Interface")
        self.resize(900, 700)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Top toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)

        self.copy_selected_btn = QPushButton("Copy Selected")
        self.copy_selected_btn.clicked.connect(self.copy_selected)
        self.copy_selected_btn.setCursor(Qt.PointingHandCursor)
        toolbar_layout.addWidget(self.copy_selected_btn)

        self.copy_all_btn = QPushButton("Copy All")
        self.copy_all_btn.clicked.connect(self.copy_all)
        self.copy_all_btn.setCursor(Qt.PointingHandCursor)
        toolbar_layout.addWidget(self.copy_all_btn)

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        toolbar_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        self.deselect_all_btn.setCursor(Qt.PointingHandCursor)
        toolbar_layout.addWidget(self.deselect_all_btn)

        toolbar_layout.addStretch()

        main_layout.addLayout(toolbar_layout)

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
        main_layout.addWidget(self.input_area)

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
        self.scroll_to_bottom()

        # Update context window
        self.update_context_window()

        # Disable input while processing
        self.input_area.set_enabled(False)

        # Generate thinking text
        thinking = self.generate_thinking_text(text)

        # Add assistant message with streaming
        assistant_msg = self.chat_area.add_message("", is_user=False, thinking_text=thinking)
        assistant_msg.start_streaming()
        self.scroll_to_bottom()

        # Simulate streaming response
        self.simulate_streaming(assistant_msg, text)

    def generate_thinking_text(self, user_text):
        """Generate simulated thinking text for the response."""
        import random
        thinking_options = [
            f"The user is asking about: '{user_text[:40]}...'\nI should provide a helpful and informative response with code examples.\nLet me structure this with clear sections and use markdown formatting.",
            f"Analyzing the query: '{user_text[:40]}...'\nThis seems like a technical question. I'll include:\n1. A clear explanation\n2. Code examples with syntax highlighting\n3. Best practices",
            f"Processing user input: '{user_text[:40]}...'\nI'll demonstrate the interface capabilities including:\n- Markdown rendering\n- Syntax highlighting\n- Response streaming",
            f"Considering how to best respond to: '{user_text[:40]}...'\nI'll focus on being clear and concise while showing off the interface features.\nMaybe include some code examples with different languages.",
            f"Planning response structure for: '{user_text[:40]}...'\nKey points to cover:\n- Direct answer to the question\n- Supporting examples\n- Visual formatting with markdown",
        ]
        return random.choice(thinking_options)

    def update_context_window(self):
        """Update the context window indicator based on conversation tokens."""
        total_tokens = 0
        for msg in self.chat_area.messages:
            total_tokens += TokenCounter.estimate_tokens(msg.text)
            if hasattr(msg, 'thinking_text') and msg.thinking_text:
                total_tokens += TokenCounter.estimate_tokens(msg.thinking_text)

        self.input_area.update_context_window(total_tokens)

    def simulate_streaming(self, message_widget, user_text):
        """Simulate a streaming LLM response."""
        # Generate a response based on user input
        response = self.generate_mock_response(user_text)

        # Stream the response word by word
        words = response.split(' ')
        self.stream_words(message_widget, words, 0)

    def stream_words(self, message_widget, words, index):
        """Stream words one at a time."""
        if index < len(words):
            word = words[index]
            if index > 0:
                word = ' ' + word
            message_widget.append_text(word)
            self.scroll_to_bottom()

            # Continue streaming
            QTimer.singleShot(50, lambda: self.stream_words(message_widget, words, index + 1))
        else:
            # Streaming complete
            message_widget.stop_streaming()
            self.input_area.set_enabled(True)

            # Update context window after response
            self.update_context_window()

    def generate_mock_response(self, user_text):
        """Generate a mock LLM response."""
        responses = [
            f"""Thank you for your message! You said: "{user_text[:50]}..."

I'm a **mock LLM** response demonstrating the streaming capabilities and **syntax highlighting** of this interface.

Here are some features I can show:

1. **Markdown formatting** with *italic* and **bold** text
2. **Syntax-highlighted code blocks** with Nord colors:

```python
# Python with Nord-themed syntax highlighting
def process_message(text: str) -> dict:
    '''Process user message and return response.'''
    result = {{
        'status': 'success',
        'message': f"Processed: {{text}}",
        'timestamp': datetime.now()
    }}
    return result
```

3. Lists and quotes
4. Even incomplete markdown like `unclosed code or **bold

The interface handles all of this gracefully!""",

            f"""Interesting! Let me respond to "{user_text[:40]}..." with some **syntax-highlighted examples**!

## Key Points:
- This interface uses the **Nord color scheme** throughout
- Messages stream in word by word with smooth animations
- **Pygments** provides professional syntax highlighting
- You can copy messages individually or all at once

> "Good code is its own best documentation." - Steve McConnell

### Technical Implementation

The markdown renderer uses Python-Markdown with CodeHilite:

```python
from markdown.extensions.codehilite import CodeHiliteExtension

md = markdown.Markdown(
    extensions=[
        CodeHiliteExtension(guess_lang=True),
        'fenced_code',
        'tables'
    ]
)
```

### TypeScript Example

Here's how you might integrate with an API:

```typescript
interface ChatMessage {{
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}}

async function sendMessage(msg: ChatMessage): Promise<Response> {{
    const response = await fetch('/api/chat', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(msg)
    }});
    return response.json();
}}
```

Notice how keywords, strings, and types all have distinct Nord colors!""",

            f"""Got your message: "{user_text}"

Let me show you **syntax highlighting across multiple languages** while also testing robust markdown handling!

### Shell Script Example:
```bash
#!/bin/bash
# Deploy script with error handling
set -euo pipefail

echo "Starting deployment..."
for service in api web worker; do
    echo "Deploying $service..."
    docker-compose up -d "$service" || exit 1
done
echo "Deployment complete!"
```

### C++ Example:
```cpp
#include <iostream>
#include <vector>

template<typename T>
class Stack {{
private:
    std::vector<T> elements;
public:
    void push(const T& elem) {{ elements.push_back(elem); }}
    T pop() {{
        T elem = elements.back();
        elements.pop_back();
        return elem;
    }}
}};
```

## Markdown Robustness Test

This has unclosed `code formatting

This has unclosed **bold formatting

This has unclosed *italic formatting

## Data Table:

| Language | Status | Colors |
|----------|--------|--------|
| Python   | ✅     | Blue, Green, Purple |
| JavaScript | ✅   | Cyan, Yellow |
| Rust     | ✅     | Full spectrum! |

Even with markdown errors, everything still displays correctly! 🎉

The interface prioritizes **showing content** over strict syntax enforcement, while providing beautiful highlighting for properly formatted code."""
        ]

        import random
        return random.choice(responses)

    def scroll_to_bottom(self):
        """Scroll chat area to bottom."""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def copy_selected(self):
        """Copy selected messages to clipboard."""
        selected = self.chat_area.get_selected_messages()
        if not selected:
            return

        text = "\n\n---\n\n".join([
            f"{'User' if msg.is_user else 'Assistant'}: {msg.text}"
            for msg in selected
        ])

        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def copy_all(self):
        """Copy all messages to clipboard."""
        text = "\n\n---\n\n".join([
            f"{'User' if msg.is_user else 'Assistant'}: {msg.text}"
            for msg in self.chat_area.messages
        ])

        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def select_all(self):
        """Select all messages."""
        for msg in self.chat_area.messages:
            msg.set_selected(True)

    def deselect_all(self):
        """Deselect all messages."""
        for msg in self.chat_area.messages:
            msg.set_selected(False)


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
