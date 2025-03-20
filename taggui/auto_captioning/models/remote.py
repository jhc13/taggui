import base64
import io
import json
from typing import Tuple

import requests
from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image
import auto_captioning.captioning_thread as captioning_thread

class RemoteGen(AutoCaptioningModel):
	def __init__(self,
					captioning_thread_: 'captioning_thread.CaptioningThread',
					caption_settings: dict):
		self.api_url = 'https://localhost:5001'
		self.set_api_url(caption_settings['api_url']) # captioning_thread_.caption_settings['api_url'] #caption_settings['api_url']
		self.headers = {"Content-Type": "application/json"}
		super().__init__(captioning_thread_, caption_settings)
		
	def get_processor(self):
		return None
	def get_model_load_arguments(self) -> dict:
		return {}  # Not used for API models.
	def load_model(self, model_load_arguments):
		return None
	def get_model(self):
		return None  # No local model for API interaction
	def set_api_url(self, remote_address:str):
		if remote_address.endswith('/generate'):
			self.api_url = remote_address
		else:
			self.api_url = remote_address + '/api/v1/generate'

	@staticmethod
	def get_default_prompt() -> str:
		return 'Describe the image in one sentence.'

	def format_prompt(self, prompt: str) -> str:
		#  LLaVA's specific conversational structure
		return (f'<|start_header_id|>user<|end_header_id|>\n\n<image>\n'
				f'{prompt}<|eot_id|><|start_header_id|>assistant'
				f'<|end_header_id|>\n\n')

	def get_input_text(self, image_prompt: str) -> str:
		return image_prompt + self.caption_start

	def get_model_inputs(self, image_prompt: str, image: Image) -> dict:
		"""
		Prepares data for the API, including base64 encoding of the image.
		"""
		text = self.get_input_text(image_prompt)

		# Load and convert the image to base64
		pil_image = self.load_image(image)
		buffered = io.BytesIO()
		pil_image.save(buffered, format="PNG")  # Use PNG for lossless encoding
		img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

		# Construct the payload, merging generation parameters
		payload = {
			"prompt": text,
			"images": [img_base64],  # API expects a list of images
			**self.generation_parameters
		}
		
		return payload

	def generate_caption(self, model_inputs: dict, image_prompt: str) -> Tuple[str, str]:
		"""
		Interacts with the API endpoint to generate the caption.
		"""
		model_inputs['max_length'] = model_inputs['max_new_tokens']
		try:
			response = requests.post(self.api_url, headers=self.headers, json=model_inputs, timeout=300) # increased timeout
			response.raise_for_status()  # Raise an exception for bad status codes
			json_response = response.json()
			caption = self.get_caption_from_generated_tokens(json_response, image_prompt)
			console_output_caption = caption
			return caption, console_output_caption
		except requests.exceptions.RequestException as e:
			print(f"Error during API request: {e}")
			return "", str(e)  # Return empty caption and error message
		except (KeyError, json.JSONDecodeError) as e:
			print(f"Error parsing API response: {e}")
			return "", str(e)
		except Exception as e:
			print(f"An unexpected error occurred: {e}")  # catch any other exceptions
			return "", str(e)
		
	@staticmethod
	def postprocess_image_prompt(image_prompt: str) -> str:
		image_prompt = image_prompt.replace('<|start_header_id|>', '')
		image_prompt = image_prompt.replace('<|end_header_id|>', '')
		image_prompt = image_prompt.replace('<image>', '')
		image_prompt = image_prompt.split('<|eot_id|>')[0]
		return image_prompt

	@staticmethod
	def postprocess_generated_text(generated_text: str) -> str:
		#remove everything after <|eot_id|>
		generated_text = generated_text.split("<|eot_id|>")[0]
		generated_text = generated_text.split("<|eot|>")[0]
		generated_text = generated_text.split("</description>")[0]

		return generated_text
	
	def get_caption_from_generated_tokens(self, json_response, image_prompt):
		try:
			# Extract text. Adapt this based on your API's response format.
			generated_text = json_response['results'][0]['text']
			generated_text = self.postprocess_generated_text(generated_text)
			if image_prompt.strip() and generated_text.startswith(image_prompt):
				caption = generated_text[len(image_prompt):]
			elif (self.caption_start.strip()
				and generated_text.startswith(self.caption_start)):
				caption = generated_text
			else:
				caption = f'{self.caption_start.strip()} {generated_text.strip()}'
			caption = caption.strip()
			if self.remove_tag_separators:
				caption = caption.replace(self.thread.tag_separator, ' ')
			return caption

		except (KeyError, IndexError) as e:
			raise ValueError(f"Unexpected API response format: {e}") from e