"""
Configuration Example for LLM Chat Interface

This file shows how to customize the chat interface for your needs.
"""

# Example: Custom color scheme (replace Nord with your own)
CUSTOM_COLORS = {
    'background': '#1e1e1e',
    'surface': '#252526',
    'surface_alt': '#2d2d30',
    'border': '#3e3e42',
    'text': '#d4d4d4',
    'text_bright': '#ffffff',
    'accent': '#007acc',
    'accent_hover': '#0098ff',
    'success': '#4ec9b0',
    'warning': '#ce9178',
    'error': '#f48771',
}

# Example: Custom streaming settings
STREAMING_CONFIG = {
    'word_delay_ms': 50,  # Delay between words in milliseconds
    'char_delay_ms': 10,  # Alternative: delay between characters
    'enable_animation': True,
    'animation_speed_ms': 200,
}

# Example: UI Configuration
UI_CONFIG = {
    'window_width': 1000,
    'window_height': 800,
    'font_family': 'SF Pro',
    'font_size': 13,
    'code_font_family': 'SF Mono',
    'input_min_height': 80,
    'input_max_height': 200,
    'message_spacing': 12,
}

# Example: Feature flags
FEATURES = {
    'enable_regenerate': True,
    'enable_view_original': True,
    'enable_copy': True,
    'enable_selection': True,
    'enable_welcome_message': True,
    'enable_streaming_animation': True,
}

# Example: Mock responses (for demo mode)
DEMO_RESPONSES = [
    "This is a custom demo response!",
    "You can configure multiple responses for testing.",
    "The interface will cycle through these randomly.",
]

# Example: API Configuration (for real LLM integration)
API_CONFIG = {
    'provider': 'openai',  # or 'anthropic', 'custom', etc.
    'api_key': 'your-api-key-here',
    'model': 'gpt-4',
    'temperature': 0.7,
    'max_tokens': 2000,
    'stream': True,
}

# Example: How to use these configs in your app
"""
To use these configurations:

1. Import them in chat_app.py:
   from config_example import CUSTOM_COLORS, STREAMING_CONFIG, UI_CONFIG

2. Replace the NORD dictionary with CUSTOM_COLORS

3. Use STREAMING_CONFIG in the stream_words method:
   QTimer.singleShot(
       STREAMING_CONFIG['word_delay_ms'],
       lambda: self.stream_words(...)
   )

4. Apply UI_CONFIG in the setup_ui methods:
   self.resize(UI_CONFIG['window_width'], UI_CONFIG['window_height'])
   font = QFont(UI_CONFIG['font_family'], UI_CONFIG['font_size'])
"""
