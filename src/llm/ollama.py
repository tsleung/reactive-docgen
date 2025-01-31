from ollama import chat
from ollama import ChatResponse
from functools import lru_cache
import logging

@lru_cache(maxsize=None)
def ollama_call(rendered_template):
  
  # response: ChatResponse = chat(model='llama3.2', messages=[
  # response: ChatResponse = chat(model='deepseek-r1:70b', messages=[
  response: ChatResponse = chat(model='deepseek-r1:1.5b', messages=[
    {
      'role': 'user',
      'content': rendered_template,
    },
  ])
  # print(response['message']['content'])
  # or access fields directly from the response object
  print(response.message.content)
  
  return response.message.content
      


if __name__ == "__main__":
  response: ChatResponse = chat(model='llama3.2', messages=[
    {
      'role': 'user',
      'content': 'Why is the sky blue?',
    },
  ])
  print(response['message']['content'])
  # or access fields directly from the response object
  print(response.message.content)