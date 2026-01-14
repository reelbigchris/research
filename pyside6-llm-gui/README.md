# PySide6 LLM Chat Interface

A modern, minimalist LLM chat interface built with PySide6 and styled with the beautiful Nord color scheme.

![Nord Theme](https://www.nordtheme.com/static/nord-logo.svg)

## Features

### 🎨 Modern Design
- Clean, minimalist interface using the Nord color palette
- Smooth animations and transitions
- Professional, distraction-free chat experience

### 📝 Robust Markdown Support
- Full markdown rendering including:
  - Headers, lists, and blockquotes
  - Code blocks with syntax highlighting
  - Tables
  - Links and formatting (bold, italic, etc.)
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

- **MessageWidget**: Individual chat message with markdown rendering
  - Selection checkbox
  - Copy, View Original, and Regenerate buttons
  - Streaming support with waiting animation
  - Auto-sizing based on content

- **ChatArea**: Scrollable container for all messages
  - Efficient layout management
  - Auto-scroll to bottom on new messages
  - Message selection tracking

- **InputArea**: Multi-line message input
  - Resizable text area
  - Send button
  - Keyboard shortcuts

- **MarkdownRenderer**: Robust markdown to HTML converter
  - Error handling for malformed markdown
  - Nord-themed styling
  - Support for code blocks, tables, lists, etc.

### Nord Color Scheme

The interface uses the Nord color palette:
- **Polar Night** (nord0-3): Dark backgrounds
- **Snow Storm** (nord4-6): Light text and foregrounds
- **Frost** (nord7-10): Blue accents
- **Aurora** (nord11-15): Colorful highlights

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
