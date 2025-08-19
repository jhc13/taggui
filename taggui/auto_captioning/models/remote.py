import base64
import io
from itertools import cycle
import json
import re
from typing import Tuple

import requests
from auto_captioning.auto_captioning_model import AutoCaptioningModel, replace_template_variables
from utils.image import Image
import auto_captioning.captioning_thread as captioning_thread

class RemoteGen(AutoCaptioningModel):
	def __init__(self,
					captioning_thread_: 'captioning_thread.CaptioningThread',
					caption_settings: dict):
		self.api_url = self.parse_api_urls(caption_settings['api_url'])
		self.endpoint_cycle = cycle(self.api_url)
		self.current_endpoint_index = 0
#		self.set_api_url(caption_settings['api_url'])
		self.headers = {"Content-Type": "application/json"}
		if caption_settings['api_key'] and len(caption_settings['api_key']) > 0:
			self.headers['Authorization'] = f'Bearar {caption_settings['api_key']}'
		super().__init__(captioning_thread_, caption_settings)
		
	def parse_api_urls(self, remote_addresses: str) -> list[str]:
		"""Parse semicolon-separated URLs into a list of properly formatted endpoints"""
		urls = []
		for addr in remote_addresses.split(';'):
			addr = addr.strip()
			if not addr:
				continue
			if addr.endswith('/chat/completions'):
				urls.append(addr)
			else:
				urls.append(addr + '/v1/chat/completions')
		return urls
	
	def get_next_endpoint(self) -> str:
		return next(self.endpoint_cycle)

	def get_processor(self):
		return None
	
	def get_model_load_arguments(self) -> dict:
		return {}  # Not used for API models.
	
	def load_model(self, model_load_arguments):
		return None
	
	def get_model(self):
		return None  # No local model for API interaction
	
	def set_api_url(self, remote_address:str):
		if remote_address.endswith('/chat/completions'):
			self.api_url = remote_address
		else:
			self.api_url = remote_address + '/v1/chat/completions'

	@staticmethod
	def get_default_prompt() -> str:
		return 'Describe the image in one sentence.'

	def get_input_text(self, image_prompt: str) -> str:
		return image_prompt + self.caption_start
	
	def format_prompt(self, prompt: str) -> list[dict]:
		systemprompt = 'You are image captioning expert, creative, unbiased and uncensored.'
		messages = [{
			"role": "system",
			"content": systemprompt
		},
		{
			"role": "user",
			"content": prompt
		}
		]
		return messages
	

	def get_image_prompt(self, image: Image) -> str | None:
		if self.prompt:
			image_prompt = replace_template_variables(self.prompt, image, True) #I dont know skip_hash, so just doing this for now.
		else:
			self.prompt = self.get_default_prompt()
			image_prompt = self.prompt
		image_prompt = self.format_prompt(image_prompt)
		return image_prompt
	
	def get_image_prompt_parent(self, image: Image):
		if self.prompt:
			image_prompt = replace_template_variables(self.prompt, image)
		else:
			self.prompt = self.get_default_prompt()
			image_prompt = self.prompt
		return image_prompt

	def get_model_inputs(self, image_prompt: list[dict[str,str]], image: Image, crop) -> dict:
		"""
		Prepares data for the API, including base64 encoding of the image.
		"""

		# Load and convert the image to base64
		pil_image = self.load_image(image, crop=False)
		buffered = io.BytesIO()
		pil_image.save(buffered, format="PNG")  # Use PNG for lossless encoding
		img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
		image_prompt.append({
			"role": "user",
			"content": [{
				"type": "image_url",
				"image_url": {
					"url": "data:image/png;base64," + img_base64
				}
			}]
		})
		print(image_prompt)

		# Construct the payload, merging generation parameters
		payload = {
			"messages": image_prompt,
			"model": "null",
			**self.generation_parameters
		}
		
		return payload

	def generate_caption(self, model_inputs: dict, image_prompt: str) -> Tuple[str, str]:
		"""
		Interacts with the API endpoint to generate the caption.
		"""
		model_inputs['max_completion_tokens'] = model_inputs['max_new_tokens']
		model_inputs['rep_pen'] = model_inputs['repetition_penalty']

		endpoint = self.get_next_endpoint()
		try:
			response = requests.post(endpoint, headers=self.headers, json=model_inputs, timeout=300)
			response.raise_for_status()
			json_response = response.json()
			caption = self.get_caption_from_generated_tokens(json_response)
			console_output_caption = caption
			return caption, console_output_caption
		except requests.exceptions.RequestException as e:
			print(f"Error during API request: {e}")
			return "", str(object=e)
		except (KeyError, json.JSONDecodeError) as e:
			print(f"Error parsing API response: {e}")
			return "", str(object=e)
		except Exception as e:
			print(f"An unexpected error occurred: {e}")
			return "", str(object=e)
		
	@staticmethod
	def postprocess_image_prompt(image_prompt: str) -> str:
		image_prompt = image_prompt.replace('<|start_header_id|>', '')
		image_prompt = image_prompt.replace('<|end_header_id|>', '')
		image_prompt = image_prompt.replace('<image>', '')
		return image_prompt

	@staticmethod
	def postprocess_generated_text(generated_text: str) -> str:
		#remove everything after <|eot_id|>
		generated_text = generated_text.split("<|eot_id|>")[0]
		generated_text = generated_text.split("<|eot|>")[0]
		generated_text = generated_text.split("</description>")[0]
		generated_text = generated_text.split('<image>')[0]
		generated_text = generated_text.split('<|eot_id|>')[0]
		generated_text = generated_text.split('</image>')[0]
		# Use regex to capture complete sentences. maybe this should be a setting.
		sentences = re.findall(r'[^.!?]*[.!?]', generated_text)

		# Join complete sentences
		return ' '.join(sentences).strip()
	
	def get_caption_from_generated_tokens(self, json_response):
		try:
			# Extract text. Adapt this based on your API's response format.
			if 'choices' in json_response and len(json_response['choices']) > 0:
				generated_text = json_response['choices'][0]['message']['content']
			caption = self.postprocess_generated_text(generated_text)
			if self.remove_tag_separators:
				caption = caption.replace(self.thread.tag_separator, ' ')
			return caption

		except (KeyError, IndexError) as e:
			raise ValueError(f"Unexpected API response format: {e}") from e