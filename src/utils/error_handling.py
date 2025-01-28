# Example of error_handling.py
class ChatError(Exception):
    """Base class for chat related errors."""
    pass

class ContextError(ChatError):
    """Error related to context creation."""
    pass

class HistoryError(ChatError):
    """Error related to chat history."""
    pass