import argparse
import sys, os
import logging
import json
import datetime
from ..rdg.functions import gemini_prompt 

from .chat_utils import create_chat_context, load_chat_history, save_chat_history, scale_chat_history

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

CHAT_HISTORY_DIR = ".rdg_chat_history"

def load_and_scale_chat_history(rdg_file, current_query, relevance_threshold=0.5):
    chat_history_dir = os.path.join(os.path.dirname(os.path.abspath(rdg_file)), CHAT_HISTORY_DIR)
    if not os.path.exists(chat_history_dir):
        return ""

    history_context = ""
    for filename in os.listdir(chat_history_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(chat_history_dir, filename)
            try:
                with open(filepath, "r") as f:
                    chat_data = json.load(f)
                    past_query = chat_data["query"]
                    past_response = chat_data["response"]
                    timestamp = datetime.datetime.strptime(filename.split(".")[0], "%Y%m%d%H%M%S")
                    age_in_days = (datetime.datetime.now() - timestamp).days
                    
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
                    
                    # Apply a linear decay based on age
                    decay_factor = max(0, 1 - (age_in_days / 30))  # Decay over 30 days
                    scaled_relevance = relevance_score * decay_factor

                    if scaled_relevance >= relevance_threshold:
                        scaled_message = f"Relevance: {scaled_relevance}\nPast Query: {past_query}\nPast Response: {past_response}\n\n"
                        history_context += scaled_message
            except Exception as e:
                logging.error(f"Error loading chat history file {filepath}: {e}")
    return history_context

def chat_cli():
    parser = argparse.ArgumentParser(description="Chat with your RDG knowledge base.")
    parser.add_argument("rdg_file", help="Path to the RDG file.")
    parser.add_argument("--session", help="Chat session ID.", default=None)
    parser.add_argument("--relevance_threshold", type=float, default=0.5, help="Relevance threshold for past chats.")
    args = parser.parse_args()

    rdg_file = args.rdg_file
    session_id = args.session if args.session else os.path.basename(rdg_file)
    
    file_dir = os.path.dirname(os.path.abspath(rdg_file))

    if not os.path.exists(rdg_file):
        print(f"Error: RDG file not found at '{rdg_file}'")
    
    print("Chat with your knowledge base. Type 'exit' to end.")
    while True:
        query = input("You: ")
        if query.lower() == "exit":
            break
        
        context = create_chat_context(rdg_file)
        history_context = load_and_scale_chat_history(rdg_file, query, args.relevance_threshold)
        prompt_template = """You are an assistant that answers questions based on the provided context. 
        Use the context to answer the question. If you cannot answer the question using the context, say 'I do not know'.

        Context:
        {context}

        Chat History:
        {history_context}

        Question:
        {query}
        """
        try:
            response = gemini_prompt(rdg_file, template=prompt_template, context=context, query=query, history_context=history_context)
            print(f"Assistant: {response}")
            save_chat_history(rdg_file, query, response, session_id)
        except Exception as e:
            logging.error(f"Error during LLM call: {e}")
            print("An error occurred while processing your request.")

if __name__ == "__main__":
    chat_cli()