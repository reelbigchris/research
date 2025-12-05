"""
Textual Streaming Chat - Complete Working Example

This demonstrates smooth, non-blocking streaming markdown in a chat interface.
Based on the architecture of Toad and Textual 4.0+ features.

Requirements:
    pip install "textual>=4.0.0"
    
For real LLM integration, also install your client:
    pip install anthropic  # or openai, httpx, etc.

Usage:
    python streaming_chat_example.py

Key Features:
    - MarkdownStream for buffered token updates (handles fast arrival)
    - container.anchor() for smart scroll management
    - @work decorator for non-blocking LLM calls
    - Incremental markdown parsing (O(1) per token, not O(N))
"""

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Vertical
from textual.widgets import Markdown, Input, Static, Footer, Header
from textual.binding import Binding
from textual import work
import asyncio


# =============================================================================
# Message Widgets
# =============================================================================

class UserMessage(Static):
    """A user message bubble aligned to the right."""
    
    DEFAULT_CSS = """
    UserMessage {
        background: $primary 20%;
        color: $text;
        margin: 1 1 1 10;
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
        margin: 1 10 1 1;
        padding: 1 2;
        border: round $secondary;
    }
    """


# =============================================================================
# Main Application
# =============================================================================

class StreamingChatApp(App):
    """
    A chat application demonstrating smooth streaming markdown.
    
    Architecture:
        1. User submits message via Input widget
        2. UserMessage widget is mounted to chat container
        3. Empty AssistantMessage widget is mounted
        4. Container is anchored (stays at bottom until user scrolls)
        5. Worker streams LLM response using MarkdownStream
        6. MarkdownStream buffers tokens and updates widget efficiently
    """
    
    TITLE = "Streaming Chat Demo"
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #chat-container {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    
    #input-area {
        height: auto;
        max-height: 10;
        dock: bottom;
        padding: 0 1;
    }
    
    Input {
        margin: 1 0;
    }
    
    /* Style the markdown code blocks */
    AssistantMessage .code-block {
        background: $surface-darken-1;
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+x", "cancel", "Cancel"),
        Binding("ctrl+l", "clear", "Clear chat"),
    ]
    
    def __init__(self):
        super().__init__()
        self._current_stream = None
        self._generating = False
        self._cancel_requested = False
    
    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()
        with VerticalScroll(id="chat-container"):
            yield Static(
                "Welcome! Type a message and press Enter to start chatting.\n"
                "Press Ctrl+X to cancel generation, Ctrl+L to clear.",
                id="welcome"
            )
        with Vertical(id="input-area"):
            yield Input(placeholder="Type your message here...", id="prompt")
        yield Footer()
    
    def on_mount(self) -> None:
        """Focus the input when app starts."""
        self.query_one("#prompt", Input).focus()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message submission."""
        # Ignore empty messages or if already generating
        if not event.value.strip():
            return
        if self._generating:
            self.notify("Please wait for the current response to complete", severity="warning")
            return
        
        prompt = event.value
        event.input.clear()
        
        # Get the chat container
        chat = self.query_one("#chat-container", VerticalScroll)
        
        # Remove welcome message if present
        try:
            welcome = self.query_one("#welcome", Static)
            await welcome.remove()
        except Exception:
            pass
        
        # Add user message to chat
        user_msg = UserMessage(prompt)
        await chat.mount(user_msg)
        
        # Add empty assistant message (will be filled by streaming)
        assistant_msg = AssistantMessage()
        await chat.mount(assistant_msg)
        
        # Anchor the container - this keeps scroll at bottom as content is added
        # but releases if user scrolls up to read history
        chat.anchor()
        
        # Start streaming response in background worker
        self.stream_response(prompt, assistant_msg)
    
    @work(exclusive=True)
    async def stream_response(self, prompt: str, message_widget: AssistantMessage) -> None:
        """
        Stream the LLM response to the message widget.
        
        This runs in a worker (background task) to avoid blocking the UI.
        Uses MarkdownStream for efficient buffered updates.
        """
        self._generating = True
        self._cancel_requested = False
        
        # Get a MarkdownStream - this handles buffering automatically
        # If tokens arrive faster than the UI can render, they're combined
        stream = Markdown.get_stream(message_widget)
        self._current_stream = stream
        
        try:
            # =================================================================
            # REPLACE THIS SECTION WITH YOUR ACTUAL LLM CLIENT
            # =================================================================
            #
            # Example with Anthropic:
            # -----------------------
            # from anthropic import AsyncAnthropic
            # client = AsyncAnthropic()
            # 
            # async with client.messages.stream(
            #     model="claude-sonnet-4-20250514",
            #     max_tokens=4096,
            #     messages=[{"role": "user", "content": prompt}]
            # ) as response:
            #     async for text in response.text_stream:
            #         if self._cancel_requested:
            #             await stream.write("\n\n*[Cancelled]*")
            #             break
            #         await stream.write(text)
            #
            # Example with OpenAI:
            # --------------------
            # from openai import AsyncOpenAI
            # client = AsyncOpenAI()
            # 
            # response = await client.chat.completions.create(
            #     model="gpt-4",
            #     messages=[{"role": "user", "content": prompt}],
            #     stream=True
            # )
            # async for chunk in response:
            #     if self._cancel_requested:
            #         await stream.write("\n\n*[Cancelled]*")
            #         break
            #     if chunk.choices[0].delta.content:
            #         await stream.write(chunk.choices[0].delta.content)
            #
            # =================================================================
            
            # DEMO MODE: Simulate streaming response
            await self._demo_stream(prompt, stream)
            
        except asyncio.CancelledError:
            await stream.write("\n\n*[Cancelled]*")
        except Exception as e:
            await stream.write(f"\n\n**Error:** {type(e).__name__}: {e}")
            self.notify(f"Error: {e}", severity="error")
        finally:
            # Always stop the stream to flush any remaining content
            await stream.stop()
            self._current_stream = None
            self._generating = False
    
    async def _demo_stream(self, prompt: str, stream) -> None:
        """
        Demo streaming - simulates an LLM response.
        Replace this with your actual LLM client.
        """
        demo_response = f"""## Response

I received your message: *"{prompt[:50]}{'...' if len(prompt) > 50 else ''}"*

Here's a demonstration of **streaming markdown** with various elements:

### Code Example

```python
from textual.widgets import Markdown

# The key to smooth streaming:
stream = Markdown.get_stream(widget)

async for token in llm_response:
    await stream.write(token)  # Buffered!

await stream.stop()  # Flush remaining content
```

### Features Demonstrated

| Feature | How It Works |
|---------|--------------|
| Buffering | Combines fast tokens into single updates |
| Incremental Parsing | Only re-parses the last block |
| Smart Scrolling | `anchor()` follows content but respects user scroll |
| Cancellation | Ctrl+X stops generation cleanly |

### Blockquote

> The `MarkdownStream` class handles the complexity of efficient 
> streaming updates so you don't have to.

### Lists

Things that make this smooth:

1. **O(1) per token** - not O(N) like naive approaches
2. **No animation queue** - anchor doesn't animate
3. **Worker isolation** - LLM calls don't block UI

That's the end of this demo! Try typing another message.
"""
        
        # Simulate token-by-token streaming with realistic timing
        # Real LLMs typically stream 50-150 tokens/second in bursts
        words = demo_response.split(' ')
        for i, word in enumerate(words):
            if self._cancel_requested:
                await stream.write("\n\n*[Generation cancelled]*")
                return
            
            # Add space back (except for last word)
            chunk = word + (' ' if i < len(words) - 1 else '')
            await stream.write(chunk)
            
            # Simulate variable network latency (20-50ms per token)
            await asyncio.sleep(0.02 + (hash(word) % 30) / 1000)
    
    def action_cancel(self) -> None:
        """Cancel the current generation."""
        if self._generating:
            self._cancel_requested = True
            self.notify("Cancelling generation...")
        else:
            self.notify("Nothing to cancel", severity="warning")
    
    def action_clear(self) -> None:
        """Clear the chat history."""
        if self._generating:
            self.notify("Cannot clear while generating", severity="warning")
            return
        
        async def do_clear():
            chat = self.query_one("#chat-container", VerticalScroll)
            await chat.remove_children()
            await chat.mount(Static(
                "Chat cleared. Type a message to start a new conversation.",
                id="welcome"
            ))
        
        self.run_worker(do_clear())


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    app = StreamingChatApp()
    app.run()
