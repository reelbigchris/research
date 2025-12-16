# LLM Chat Interface

A simple, self-contained chat interface for OpenAI-compatible APIs with support for reasoning/thinking tokens.

## Features

- **OpenAI-compatible API** - Works with any endpoint that follows the OpenAI chat completions format
- **Streaming responses** - Real-time token streaming
- **Reasoning/thinking support** - Handles both `reasoning_content` field and `<thinking>`/`<answer>` tags
- **Collapsible thinking blocks** - See the model's reasoning process
- **Markdown rendering** - Full markdown support with syntax highlighting
- **Skills/context system** - Define reusable context snippets that can be toggled on/off
- **Drag-and-drop files** - Drop text files directly into the chat to add context
- **Context window estimation** - Rough token count to track usage
- **Import/Export** - Save and load conversations as JSON
- **Local persistence** - Conversation and settings saved to localStorage
- **Keyboard shortcuts** - Ctrl+Enter to send, Escape to stop

## Setup

### 1. Download dependencies

You need to download two libraries and place them in the `lib/` folder:

#### marked (Markdown parser)
Download from: https://cdn.jsdelivr.net/npm/marked/marked.min.js

Save to: `lib/marked/marked.min.js`

#### highlight.js (Syntax highlighting)
Download from: 
- https://cdn.jsdelivr.net/gh/highlightjs/cdn-release/build/highlight.min.js
- https://cdn.jsdelivr.net/gh/highlightjs/cdn-release/build/styles/github-dark.min.css

Save to:
- `lib/highlight/highlight.min.js`
- `lib/highlight/github-dark.min.css`

### 2. Folder structure

After setup, your folder should look like:

```
llm-chat/
├── index.html
├── README.md
├── css/
│   └── styles.css
├── js/
│   └── app.js
└── lib/
    ├── marked/
    │   └── marked.min.js
    └── highlight/
        ├── highlight.min.js
        └── github-dark.min.css
```

### 3. Open in browser

Just open `index.html` in your browser. No server required.

## Configuration

1. Click the hamburger menu (☰) to open the sidebar
2. Enter your API endpoint URL (e.g., `https://your-proxy/v1/chat/completions`)
3. Enter the model name
4. Optionally configure:
   - Enable reasoning and set token budget
   - Add a system prompt
   - Create skills (reusable context snippets)

## Thinking/Reasoning Support

The interface supports two formats for reasoning tokens:

### OpenAI-style `reasoning_content`
If your API returns reasoning in the `delta.reasoning_content` field, it will be captured automatically.

### XML-style tags
If your model outputs `<thinking>...</thinking>` and `<answer>...</answer>` tags in the content, those will be parsed and displayed appropriately.

## Skills

Skills are reusable context snippets that get appended to your system prompt when enabled.

Example uses:
- Database schema documentation
- Project-specific context
- Coding conventions
- Domain knowledge

Click "Add Skill" to create one, then toggle it on/off with the checkbox.

## Keyboard Shortcuts

- `Ctrl+Enter` - Send message
- `Shift+Enter` - New line in input
- `Escape` - Stop generation

## Export Format

Exported JSON includes:
- Configuration (endpoint, model, system prompt, etc.)
- Skills (including enabled state)
- Full message history with thinking content

## Notes

- The token estimation is rough (~4 chars per token)
- Files dropped must be text-based (.txt, .md, .json, .py, .c, .h, .sql, etc.)
- localStorage is used for persistence - clearing browser data will reset everything
