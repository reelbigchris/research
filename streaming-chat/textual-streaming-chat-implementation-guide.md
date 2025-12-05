# Building a Smooth, Non-Blocking Conversation View in Textual

## Overview

This document provides everything needed to implement a CLI AI agent conversation view using Python's Textual framework (v4.0+). The key challenges are:

1. **Smooth scrolling** as messages are added
2. **No UI lock-ups** during LLM streaming
3. **Efficient markdown rendering** that scales with conversation length

This guide is based on the architecture of "Toad" (Will McGugan's universal AI terminal interface) and the optimizations built into Textual 4.0+.

---

## Required Dependencies

```bash
pip install "textual>=4.0.0"
# For your LLM client (example):
pip install anthropic  # or openai, etc.
```

Minimum Textual version: **4.0.0** (released July 2025) - this is when streaming Markdown support was added.

---

## Core Concepts

### Why Traditional Approaches Fail

**Problem 1: O(N) Markdown Parsing**
The naive approach of replacing the entire Markdown widget content on each token causes:
- Re-parsing the entire document (grows with conversation length)
- Re-creating all child widgets (paragraphs, code blocks, tables are each widgets)
- Event loop starvation when tokens arrive faster than rendering

**Problem 2: Scroll Position Management**
- Using `scroll_end(animate=True)` on every update queues animations
- The UI lags behind the data, scrollbar behaves erratically
- User scroll position is lost when they try to read history

### Textual 4.0+ Solutions

1. **`Markdown.append()`** - Incremental updates that only re-parse the last block
2. **`Markdown.get_stream()`** - Returns a `MarkdownStream` that buffers fast token arrival
3. **`container.anchor()`** - Keeps scroll at bottom until user scrolls up, then stays put

---

## The MarkdownStream API

### Key Methods

```python
from textual.widgets import Markdown

# Get a stream manager for a Markdown widget
stream = Markdown.get_stream(markdown_widget)

# Write markdown fragments (tokens from LLM)
await stream.write(chunk)  # Buffers if UI can't keep up

# Stop the stream when done
await stream.stop()
```

### How Buffering Works

If you append to the Markdown document faster than ~20 times per second, the widget can't update fast enough. The `MarkdownStream`:
- Accumulates fragments that arrive before the previous update finishes
- Combines multiple tokens into a single update
- Ensures the display is only milliseconds behind the data

---

## The Anchor API

### Changed Semantics in Textual 4.0

```python
from textual.containers import VerticalScroll

container = self.query_one(VerticalScroll)
container.anchor()  # Apply to the CONTAINER, not the content widget
```

**Behavior:**
- When anchored, the container stays scrolled to the bottom as content grows
- If the user scrolls up to read history, the anchor is released
- The view won't jump back to the bottom while the user is reading
- When the user scrolls back to the bottom, anchoring resumes

---

## Complete Working Example

```python
"""
Textual Streaming Chat - Complete Example
Requires: textual>=4.0.0, anthropic (or your LLM client)
"""

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Vertical
from textual.widgets import Markdown, Input, Static, Footer
from textual.binding import Binding
from textual import work
import asyncio


class UserMessage(Static):
    """A user message bubble."""
    DEFAULT_CSS = """
    UserMessage {
        background: $primary 20%;
        color: $text;
        margin: 1 1 1 8;
        padding: 1 2;
        border: round $primary;
    }
    """


class AssistantMessage(Markdown):
    """An assistant message that renders streaming markdown."""
    DEFAULT_CSS = """
    AssistantMessage {
        background: $surface;
        color: $text;
        margin: 1 8 1 1;
        padding: 1 2;
        border: round $secondary;
    }
    """


class ChatApp(App):
    """A chat application with smooth streaming markdown."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #chat-container {
        height: 1fr;
        border: solid $primary;
    }
    
    #input-area {
        height: auto;
        max-height: 10;
        dock: bottom;
    }
    
    Input {
        margin: 1;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "cancel", "Cancel generation"),
    ]
    
    def __init__(self):
        super().__init__()
        self._current_stream = None
        self._generating = False
    
    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        with VerticalScroll(id="chat-container"):
            # Initial empty state - messages will be mounted here
            pass
        with Vertical(id="input-area"):
            yield Input(placeholder="Type your message...", id="prompt")
        yield Footer()
    
    def on_mount(self) -> None:
        """Focus the input when app starts."""
        self.query_one("#prompt", Input).focus()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message submission."""
        if not event.value.strip() or self._generating:
            return
        
        prompt = event.value
        event.input.clear()
        
        # Get the chat container
        chat = self.query_one("#chat-container", VerticalScroll)
        
        # Add user message
        await chat.mount(UserMessage(prompt))
        
        # Add assistant message placeholder
        assistant_msg = AssistantMessage()
        await chat.mount(assistant_msg)
        
        # Anchor the container to follow new content
        chat.anchor()
        
        # Start streaming response
        self.stream_response(prompt, assistant_msg)
    
    @work(exclusive=True)
    async def stream_response(self, prompt: str, message_widget: AssistantMessage) -> None:
        """Stream the LLM response to the message widget."""
        self._generating = True
        
        # Get a MarkdownStream for buffered updates
        stream = Markdown.get_stream(message_widget)
        self._current_stream = stream
        
        try:
            # === REPLACE THIS SECTION WITH YOUR LLM CLIENT ===
            # Example using Anthropic:
            #
            # from anthropic import AsyncAnthropic
            # client = AsyncAnthropic()
            # 
            # async with client.messages.stream(
            #     model="claude-sonnet-4-20250514",
            #     max_tokens=4096,
            #     messages=[{"role": "user", "content": prompt}]
            # ) as response:
            #     async for text in response.text_stream:
            #         await stream.write(text)
            #
            # === END LLM CLIENT SECTION ===
            
            # Demo: Simulate streaming response
            demo_response = f"""# Response to: {prompt}

This is a **simulated streaming response** demonstrating smooth markdown rendering.

## Features

- Incremental parsing (only re-parses the last block)
- Buffered updates (combines fast tokens)
- Anchored scrolling (follows content, respects user scroll)

## Code Example

```python
async def stream_response(self, prompt: str):
    stream = Markdown.get_stream(widget)
    async for chunk in llm.stream(prompt):
        await stream.write(chunk)
    await stream.stop()
```

## Table Example

| Feature | Status |
|---------|--------|
| Streaming | ✅ Working |
| Scrolling | ✅ Smooth |
| Performance | ✅ O(1) per token |

> The quick brown fox jumps over the lazy dog.
> This demonstrates blockquote rendering.

That's the end of this demo response!
"""
            # Simulate token-by-token streaming
            words = demo_response.split(' ')
            for i, word in enumerate(words):
                if self._current_stream is None:
                    break  # Cancelled
                chunk = word + (' ' if i < len(words) - 1 else '')
                await stream.write(chunk)
                await asyncio.sleep(0.02)  # Simulate network latency
            
        except Exception as e:
            await stream.write(f"\n\n**Error:** {e}")
        finally:
            await stream.stop()
            self._current_stream = None
            self._generating = False
    
    def action_cancel(self) -> None:
        """Cancel the current generation."""
        if self._current_stream:
            self._current_stream = None
            self._generating = False
            self.notify("Generation cancelled")


if __name__ == "__main__":
    app = ChatApp()
    app.run()
```

---

## Integration with Real LLM Clients

### Anthropic (Claude)

```python
from anthropic import AsyncAnthropic

@work(exclusive=True)
async def stream_response(self, prompt: str, widget: Markdown) -> None:
    client = AsyncAnthropic()
    stream = Markdown.get_stream(widget)
    
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        ) as response:
            async for text in response.text_stream:
                await stream.write(text)
    finally:
        await stream.stop()
```

### OpenAI

```python
from openai import AsyncOpenAI

@work(exclusive=True)
async def stream_response(self, prompt: str, widget: Markdown) -> None:
    client = AsyncOpenAI()
    stream = Markdown.get_stream(widget)
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )
        async for chunk in response:
            if chunk.choices[0].delta.content:
                await stream.write(chunk.choices[0].delta.content)
    finally:
        await stream.stop()
```

### Local Models (Ollama)

```python
import httpx

@work(exclusive=True)
async def stream_response(self, prompt: str, widget: Markdown) -> None:
    stream = Markdown.get_stream(widget)
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "http://localhost:11434/api/generate",
                json={"model": "llama2", "prompt": prompt},
                timeout=None
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "response" in data:
                            await stream.write(data["response"])
    finally:
        await stream.stop()
```

---

## Multi-Turn Conversation Pattern

For a full chat with history:

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str

class ChatApp(App):
    def __init__(self):
        super().__init__()
        self.conversation: List[Message] = []
    
    @work(exclusive=True)
    async def stream_response(self, prompt: str, widget: Markdown) -> None:
        # Add user message to history
        self.conversation.append(Message("user", prompt))
        
        # Build messages for API
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in self.conversation
        ]
        
        stream = Markdown.get_stream(widget)
        full_response = ""
        
        try:
            async with client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=messages
            ) as response:
                async for text in response.text_stream:
                    full_response += text
                    await stream.write(text)
            
            # Add assistant response to history
            self.conversation.append(Message("assistant", full_response))
        finally:
            await stream.stop()
```

---

## Advanced: Custom Styling

### CSS Variables Available

```css
/* Textual's built-in design tokens */
$background      /* App background */
$surface         /* Widget surfaces */
$primary         /* Primary accent color */
$secondary       /* Secondary accent color */
$text            /* Default text color */
$text-muted      /* Muted text */
$success         /* Success states */
$warning         /* Warning states */
$error           /* Error states */
```

### Styling Markdown Blocks

The Markdown widget uses component classes for different block types:

```css
/* Target code blocks */
Markdown .code-block {
    background: $surface;
    border: solid $primary;
    padding: 1;
}

/* Target blockquotes */
Markdown .block-quote {
    border-left: thick $secondary;
    padding-left: 2;
    color: $text-muted;
}

/* Target tables */
Markdown .markdown-table {
    margin: 1 0;
}

/* Target headings */
Markdown .h1 {
    color: $primary;
    text-style: bold;
}
```

---

## Performance Considerations

### Why This Approach is O(1) Per Token

1. **Finalized blocks are never re-parsed**: Once a paragraph/code block/table is complete, it's cached
2. **Only the last block is re-parsed**: The parser stores where the last block started
3. **In-place widget updates**: If block type doesn't change, the widget is updated not replaced
4. **Buffered rendering**: Multiple tokens become one UI update

### What to Avoid

```python
# ❌ BAD: Replaces entire content (O(N) per token)
full_text += token
await markdown_widget.update(full_text)

# ❌ BAD: Animated scroll on every update (queues animations)
container.scroll_end(animate=True)

# ✅ GOOD: Use the streaming API
await stream.write(token)

# ✅ GOOD: Anchor once, let it handle scroll
container.anchor()
```

---

## Handling Edge Cases

### User Scrolls During Generation

The `anchor()` method handles this automatically:
- User scrolls up → anchor releases, view stays where user scrolled
- User scrolls back to bottom → anchor re-engages
- No special code needed

### Cancellation

```python
class ChatApp(App):
    def __init__(self):
        super().__init__()
        self._cancel_event = asyncio.Event()
    
    @work(exclusive=True)
    async def stream_response(self, prompt: str, widget: Markdown) -> None:
        self._cancel_event.clear()
        stream = Markdown.get_stream(widget)
        
        try:
            async for text in llm_stream(prompt):
                if self._cancel_event.is_set():
                    await stream.write("\n\n*[Generation cancelled]*")
                    break
                await stream.write(text)
        finally:
            await stream.stop()
    
    def action_cancel(self) -> None:
        self._cancel_event.set()
```

### Error Handling

```python
@work(exclusive=True)
async def stream_response(self, prompt: str, widget: Markdown) -> None:
    stream = Markdown.get_stream(widget)
    
    try:
        async for text in llm_stream(prompt):
            await stream.write(text)
    except httpx.TimeoutException:
        await stream.write("\n\n**Error:** Request timed out")
    except Exception as e:
        await stream.write(f"\n\n**Error:** {e}")
    finally:
        await stream.stop()
```

---

## The "Stream" Layout (Experimental)

Textual 5.x added an undocumented `stream` layout that's faster than `vertical` for streaming content:

```css
#chat-container {
    layout: stream;  /* Faster than 'vertical' for streaming */
}
```

This layout has fewer CSS rules supported but is optimized for the streaming use case. Use with caution as it's undocumented.

---

## Summary Checklist

- [ ] Using Textual >= 4.0.0
- [ ] Using `Markdown.get_stream()` instead of `Markdown.update()`
- [ ] Calling `container.anchor()` on the VerticalScroll container
- [ ] Using `@work` decorator for LLM streaming
- [ ] Using `async for` to stream tokens
- [ ] Calling `await stream.stop()` in a `finally` block
- [ ] Not using `scroll_end(animate=True)` on every update

---

## API Reference Quick Look

### Markdown

```python
class Markdown(Widget):
    def append(self, markdown: str) -> AwaitComplete:
        """Append markdown fragment. Returns awaitable."""
    
    @classmethod
    def get_stream(cls, markdown: Markdown) -> MarkdownStream:
        """Get a MarkdownStream for buffered streaming."""
    
    def update(self, markdown: str) -> AwaitComplete:
        """Replace entire content. Avoid for streaming."""
```

### MarkdownStream

```python
class MarkdownStream:
    async def write(self, markdown_fragment: str) -> None:
        """Append or enqueue a markdown fragment."""
    
    async def stop(self) -> None:
        """Stop the stream and await completion."""
    
    def start(self) -> None:
        """Start background updater. Auto-called by get_stream()."""
```

### Widget.anchor()

```python
class Widget:
    def anchor(self) -> None:
        """Anchor scrollable widget to bottom.
        
        Stays at bottom when content added.
        Releases when user scrolls up.
        Re-engages when user scrolls to bottom.
        """
```

---

## Resources

- Textual Documentation: https://textual.textualize.io/
- Textual GitHub: https://github.com/Textualize/textual
- Markdown Widget Docs: https://textual.textualize.io/widgets/markdown/
- Will McGugan's Streaming Markdown Blog Post: https://willmcgugan.github.io/streaming-markdown/
