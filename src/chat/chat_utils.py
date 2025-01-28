import os
import json
import datetime
import logging
from ..rdg.functions import gemini_prompt
from .chat_context import create_chat_context_from_rdg

CHAT_HISTORY_DIR = ".rdg_chat_history"

def create_chat_context(rdg_file: str) -> str:
    """Creates a context string from the output files specified in the RDG file."""
    return create_chat_context_from_rdg(rdg_file)

def load_chat_history(rdg_file: str, session_id: str = None) -> list:
    """Loads chat history from the chat history directory."""
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    chat_history_dir = os.path.join(rdg_dir, CHAT_HISTORY_DIR)
    history = []
    if not os.path.exists(chat_history_dir):
        return history
    for filename in os.listdir(chat_history_dir):
        if filename.endswith(".json") and (session_id is None or filename.startswith(session_id)):
            filepath = os.path.join(chat_history_dir, filename)
            try:
                with open(filepath, "r") as f:
                    chat_data = json.load(f)
                    history.append(chat_data)
            except Exception as e:
                logging.error(f"Error loading chat history file {filepath}: {e}")
    return history

def save_chat_history(rdg_file: str, query: str, response: str, session_id: str = None):
    """Saves the chat interaction to a file."""
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    chat_history_dir = os.path.join(rdg_dir, CHAT_HISTORY_DIR)
    os.makedirs(chat_history_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{session_id}_{timestamp}.json" if session_id else f"{timestamp}.json"
    file_path = os.path.join(chat_history_dir, file_name)

    try:
        with open(file_path, "w") as f:
            json.dump({"query": query, "response": response}, f)
    except Exception as e:
        logging.error(f"Error saving chat history: {e}")

def scale_chat_history(rdg_file: str, current_query: str, chat_history: list) -> str:
    """Scales the importance of past chats based on relevance to the current query."""
    history_context = ""
    for chat_data in chat_history:
        past_query = chat_data["query"]
        past_response = chat_data["response"]

        relevance_prompt = f"""
        You are an assistant that determines the relevance of a past chat message to the current question.
        
        Past Chat Message:
        Query: {past_query}
        Response: {past_response}
        
        Current Question:
        {current_query}
        
        Is the past chat message relevant to the current question? Answer with a number between 0 and 1, where 0 means not relevant and 1 means highly relevant.
        """
        relevance_score = gemini_prompt(rdg_file, template=relevance_prompt)
        try:
            relevance_score = float(relevance_score)
        except ValueError:
            relevance_score = 0  # Default to 0 if not a valid number
        
        scaled_message = f"Relevance: {relevance_score}\nPast Query: {past_query}\nPast Response: {past_response}\n\n"
        history_context += scaled_message
    return history_context