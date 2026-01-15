# PySide6 LLM Chat Interface

A modern, minimalist LLM chat interface built with PySide6 and styled with the beautiful Nord color scheme.

![Nord Theme](https://www.nordtheme.com/static/nord-logo.svg)

## Features

### 🎨 Modern Design
- Clean, minimalist interface using the Nord color palette
- Smooth animations and transitions
- Professional, distraction-free chat experience

### 📝 Robust Markdown Support with Syntax Highlighting
- Full markdown rendering using **Python-Markdown** including:
  - Headers, lists, and blockquotes
  - **Pygments-powered syntax highlighting** for code blocks
  - Tables (GitHub Flavored Markdown)
  - Links and formatting (bold, italic, etc.)
- **Nord-themed syntax colors**:
  - Keywords: Blue (`nord9`)
  - Strings: Green (`nord14`)
  - Comments: Gray (`nord3`)
  - Functions: Cyan (`nord8`)
  - Numbers: Purple (`nord15`)
  - Classes: Teal (`nord7`)
  - And more...
- Automatic language detection for code blocks
- Graceful error handling for malformed markdown
- Prioritizes content display over strict syntax enforcement

### ⚡ Streaming Support
- Real-time message streaming simulation
- Animated waiting indicator
- Smooth text updates as responses arrive
- Non-blocking UI during streaming

### 📋 Copy Functionality
- Copy individual messages with one click
- Select multiple messages using checkboxes
- Copy all messages in the conversation
- Select/Deselect all with toolbar buttons

### 🔄 Message Management
- **View Original**: See the raw markdown of any assistant message
- **Regenerate**: Request a new response (button ready for integration)
- Left-aligned message boxes for both user and assistant
- Clear visual distinction between user and assistant messages

### ⌨️ Keyboard Shortcuts
- `Ctrl+Enter`: Send message
- Multi-line text input with auto-resize
- Smooth scrolling to latest messages

### 🔬 Advanced Features (NEW!)

**Token Management:**
- **Real-time token counter**: Displays estimated token count as you type
- **Context window indicator**: Shows total conversation tokens vs max (default 4096)
- Color-coded warnings (green → yellow → red) as you approach limits

**Performance Metrics:**
- **Response time tracking**: Precise timing for each assistant response
- **Token count per message**: Automatic estimation for all messages
- **Tokens per second**: Real-time throughput metrics during streaming
- **Message timestamps**: Track when each message was sent (HH:MM:SS format)

**Thinking Box (Extended Thinking):**
- Expandable section showing the model's reasoning process
- Click "▶ View Thinking" to expand, "▼ Hide Thinking" to collapse
- Styled differently from main content (darker background, italic text)
- Optional - only appears when thinking text is available

**Enhanced Animations:**
- Improved "Thinking..." indicator with smooth dot animation
- Shows metrics after streaming completes
- Non-blocking animations that don't interfere with UI responsiveness

## Installation

1. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the application:
```bash
python chat_app.py
```

Or make it executable:
```bash
chmod +x chat_app.py
./chat_app.py
```

## Architecture

### Components

- **TokenCounter**: Simple but effective token estimation utility
  - Estimates tokens using character and word-based heuristics (~1 token per 4 characters)
  - Good enough for UI feedback without requiring heavyweight tokenizers
  - Format helper for displaying counts with percentages

- **MessageWidget**: Individual chat message with markdown rendering
  - Selection checkbox
  - Copy, View Original, and Regenerate buttons
  - Streaming support with improved "Thinking..." animation
  - **Timestamp display** showing when message was sent
  - **Response metrics** (time, tokens, tokens/sec) for assistant messages
  - **Expandable thinking box** for viewing model reasoning
  - Auto-sizing based on content

- **ChatArea**: Scrollable container for all messages
  - Efficient layout management
  - Auto-scroll to bottom on new messages
  - Message selection tracking
  - Support for thinking text in assistant messages

- **InputArea**: Multi-line message input with live feedback
  - Resizable text area
  - Send button
  - Keyboard shortcuts (Ctrl+Enter)
  - **Real-time token counter** that updates as you type
  - **Context window indicator** showing conversation token usage
  - Color-coded warnings for token limits

- **MarkdownRenderer**: Robust markdown to HTML converter with syntax highlighting
  - Integrates Python-Markdown with CodeHilite extension
  - Pygments for professional syntax highlighting
  - Custom Nord-themed CSS for all syntax tokens
  - Automatic language detection (supports 500+ languages)
  - Error handling for malformed markdown
  - Support for code blocks, tables, lists, etc.

### Nord Color Scheme

The interface uses the Nord color palette:
- **Polar Night** (nord0-3): Dark backgrounds
- **Snow Storm** (nord4-6): Light text and foregrounds
- **Frost** (nord7-10): Blue accents
- **Aurora** (nord11-15): Colorful highlights

### Syntax Highlighting

The interface features **Pygments-powered syntax highlighting** with a custom Nord theme:

**Supported Languages** (500+ total, popular ones include):
- Python, JavaScript, TypeScript, Java, C, C++, C#
- Rust, Go, Ruby, PHP, Swift, Kotlin
- Shell/Bash, PowerShell, SQL, HTML, CSS
- JSON, YAML, XML, Markdown
- And many more...

**Nord Color Mapping for Code:**
```python
# Example showing Nord colors in action
class MarkdownRenderer:  # Classes: nord7 (teal)
    def __init__(self):  # Keywords: nord9 (blue)
        # Comments: nord3 (gray)
        self.md = markdown.Markdown(  # Functions: nord8 (cyan)
            extensions=['codehilite']  # Strings: nord14 (green)
        )
        self.count = 42  # Numbers: nord15 (purple)
```

The syntax highlighter automatically detects the language from the code fence identifier (e.g., ` ```python `) and applies appropriate Nord-themed colors for maximum readability.

## Integration with Real LLM

To integrate with a real LLM API:

1. Replace the `simulate_streaming` method in `MainWindow`
2. Connect to your LLM API (OpenAI, Anthropic, etc.)
3. Stream responses token by token using `message_widget.append_text(token)`
4. Call `message_widget.stop_streaming()` when complete

Example:
```python
async def stream_llm_response(self, message_widget, user_text):
    """Stream real LLM response."""
    message_widget.start_streaming()

    async for token in llm_api.stream(user_text):
        message_widget.append_text(token)
        self.scroll_to_bottom()

    message_widget.stop_streaming()
    self.input_area.set_enabled(True)
```

## Customization

### Changing Colors

Edit the `NORD` dictionary in `chat_app.py` to use different colors:
```python
NORD = {
    'nord0': '#2E3440',  # Background
    'nord4': '#D8DEE9',  # Text
    # ... etc
}
```

### Adjusting Streaming Speed

Modify the timer delay in `stream_words`:
```python
QTimer.singleShot(50, ...)  # 50ms delay between words
```

### Font Customization

Change the font in the `main()` function:
```python
font = QFont("Your Font Name", 13)
app.setFont(font)
```

## Dependencies

- **PySide6** (>=6.6.0): Qt bindings for Python
- **markdown** (>=3.5.0): Markdown to HTML conversion
- **Pygments** (>=2.17.0): Syntax highlighting support

## License

MIT License - feel free to use and modify for your projects!

## Screenshots

The interface includes:
- A welcome message demonstrating markdown capabilities
- Mock responses showing various formatting options
- Toolbar with copy and selection controls
- Clean, professional design

Try it out and see the Nord theme in action!
