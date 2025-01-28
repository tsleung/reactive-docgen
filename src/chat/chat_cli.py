import argparse
import os
import logging
from ..rdg.functions import gemini_prompt_template 

from .chat_utils import create_chat_context, load_chat_history, save_chat_history, unscaled_chat_history

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

CHAT_HISTORY_DIR = ".rdg_chat_history"

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
    
    chat_context = create_chat_context(rdg_file)
    print("Chat with your knowledge base. Type 'exit' to end.")
    
    chat_history = load_chat_history(rdg_file, session_id)
    
    while True:
        query = input("You: ")
        if query.lower() == "exit":
            break
        
        context = create_chat_context(rdg_file)
        scaled_history = unscaled_chat_history(rdg_file, query, chat_history)
        
        prompt_template = """You are an assistant that answers questions based on the provided context. 
        Use the context to answer the question. If you cannot answer the question using the context, say 'I do not know'.

        Context:
        ${context}
        
        Past Chat History:
        ${scaled_history}

        Question:
        ${query}
        """
        try:
            response = gemini_prompt_template(rdg_file, template=prompt_template, context=context, query=query, scaled_history=scaled_history)
            print(f"Assistant: {response}")
            save_chat_history(rdg_file, query, response, session_id)
            chat_history.append({"query": query, "response": response})
        except Exception as e:
            logging.error(f"Error during LLM call: {e}")
            print("An error occurred while processing your request.")

if __name__ == "__main__":
    chat_cli()