"""Auto-captioning through a local LM Studio or Ollama server.

No model is downloaded or loaded by TagGUI. Each image is sent (base64) to
whatever model is loaded in LM Studio / Ollama, together with the prompt box
text (user prompt) and the system prompt from the settings.
"""
import base64
import io
import json
import re
import urllib.error
import urllib.request
from datetime import datetime

from PIL import Image as PilImage
from PIL.ImageOps import exif_transpose

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image

LM_STUDIO_MODEL_ID = 'LM Studio (local server)'
OLLAMA_MODEL_ID = 'Ollama (local server)'
LOCAL_SERVER_MODEL_IDS = (LM_STUDIO_MODEL_ID, OLLAMA_MODEL_ID)

DEFAULT_LM_STUDIO_URL = 'http://localhost:1234'
DEFAULT_OLLAMA_URL = 'http://localhost:11434'
DEFAULT_USER_PROMPT = (
    'Analyze the image and output a comprehensive, comma-separated list of '
    'e621-style tags. Include ratings (safe, questionable, explicit), '
    'species, gender/sex characteristics, character names, copyright/source '
    'if recognizable, and detailed general tags covering clothing, '
    'expression, pose, anatomy, background, framing, and objects, using '
    'standard e621 formatting with underscores for multi-word tags. Provide '
    'only the raw tags without full sentences or conversational filler.')
DEFAULT_SYSTEM_PROMPT = (
    'You are an expert image tagger for e621-style datasets. Look carefully '
    'at the image and answer only with what the user asks for. Output a '
    'single line of comma-separated tags, with no numbering, explanations or '
    'other text. Do not mention watermarks or signatures.')
# Longest image side sent to the server. Larger images are downscaled.
MAX_IMAGE_SIDE = 2048


def is_local_server_model(model_id: str) -> bool:
    return model_id in LOCAL_SERVER_MODEL_IDS


def strip_think(text: str) -> str:
    """Remove reasoning blocks such as `<think>...</think>`."""
    text = re.sub(r'<(think|thinking|reasoning)>.*?</\1>', '', text,
                  flags=re.DOTALL | re.IGNORECASE)
    # A closing tag without an opening tag (the template opened it).
    match = re.search(r'</(think|thinking|reasoning)>', text, re.IGNORECASE)
    if match:
        text = text[match.end():]
    # An opening tag that was never closed (ran out of tokens while thinking).
    text = re.split(r'<(?:think|thinking|reasoning)>', text,
                    flags=re.IGNORECASE)[0]
    return text.strip()


def clean_tag_list(text: str, separator: str) -> str:
    """Normalize a comma/newline-separated tag list."""
    text = text.strip().strip('`').strip()
    parts = re.split(r'[,\n]+', text)
    tags = []
    seen = set()
    for part in parts:
        tag = part.strip().strip('-*\u2022').strip().rstrip('.').strip()
        if tag.lower().startswith('tags:'):
            tag = tag[5:].strip()
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        tags.append(tag)
    return separator.join(tags)


def encode_image(path, max_side: int = MAX_IMAGE_SIDE) -> str:
    pil_image = PilImage.open(path)
    pil_image = exif_transpose(pil_image)
    pil_image = pil_image.convert('RGB')
    if max(pil_image.size) > max_side:
        pil_image.thumbnail((max_side, max_side), PilImage.LANCZOS)
    buffer = io.BytesIO()
    pil_image.save(buffer, format='JPEG', quality=95)
    return base64.b64encode(buffer.getvalue()).decode('ascii')


def http_json(url: str, payload: dict | None = None,
              timeout: float = 600) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method='POST' if data else 'GET')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        body = error.read().decode('utf-8', errors='replace')
        raise LocalServerError(f'Server returned HTTP {error.code} for {url}: '
                               f'{body[:500]}') from None


class LocalServerError(Exception):
    pass


class LocalServerBackend:
    name = ''

    def __init__(self, base_url: str, model: str = ''):
        self.base_url = base_url.strip().rstrip('/')
        # Allow users to paste the URL with `/v1` or `/api`.
        self.base_url = re.sub(r'/(v1|api)$', '', self.base_url)
        self.model = model.strip()

    def check(self, timeout: float = 5) -> str:
        """Check the server and return the model name to use."""
        raise NotImplementedError

    def caption(self, image_b64: str, user_prompt: str, system_prompt: str,
                max_tokens: int, temperature: float,
                timeout: float = 600) -> str:
        raise NotImplementedError

    def unreachable_error(self, error: Exception) -> LocalServerError:
        return LocalServerError(
            f'Could not reach the {self.name} server at {self.base_url} '
            f'({error}). Make sure {self.name} is running and its local '
            f'server is started, and that the server URL is correct.')


class LmStudioBackend(LocalServerBackend):
    name = 'LM Studio'

    def check(self, timeout: float = 5) -> str:
        if self.model:
            return self.model
        try:
            # LM Studio's REST API shows which models are currently loaded.
            try:
                response = http_json(f'{self.base_url}/api/v0/models',
                                     timeout=timeout)
                models = response.get('data', [])
                loaded = [m for m in models if m.get('state') == 'loaded']
                vision = [m for m in loaded if m.get('type') == 'vlm']
                chosen = (vision or loaded)
                if chosen:
                    self.model = chosen[0]['id']
                    return self.model
                if models:
                    raise LocalServerError(
                        'No model is loaded in LM Studio. Load a vision '
                        'model (for example Qwen3.5-9B with its mmproj) in '
                        'LM Studio, or type a model name in the "Model name" '
                        'field.')
            except LocalServerError as error:
                if 'No model is loaded' in str(error):
                    raise
            # Fall back to the OpenAI-compatible endpoint.
            response = http_json(f'{self.base_url}/v1/models',
                                 timeout=timeout)
        except (urllib.error.URLError, OSError) as error:
            raise self.unreachable_error(error) from None
        models = response.get('data', [])
        if not models:
            raise LocalServerError(
                'No model is loaded in LM Studio. Load a vision model in LM '
                'Studio, or type a model name in the "Model name" field.')
        self.model = models[0]['id']
        return self.model

    def caption(self, image_b64, user_prompt, system_prompt, max_tokens,
                temperature, timeout=600) -> str:
        messages = []
        if system_prompt.strip():
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': [
            {'type': 'text', 'text': user_prompt},
            {'type': 'image_url',
             'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'}}
        ]})
        payload = {'model': self.model, 'messages': messages,
                   'max_tokens': max_tokens, 'temperature': temperature,
                   'stream': False}
        try:
            response = http_json(f'{self.base_url}/v1/chat/completions',
                                 payload, timeout=timeout)
        except (urllib.error.URLError, OSError) as error:
            raise self.unreachable_error(error) from None
        if 'error' in response:
            raise LocalServerError(f'LM Studio error: {response["error"]}')
        try:
            text = response['choices'][0]['message'].get('content') or ''
        except (KeyError, IndexError):
            raise LocalServerError(
                f'Unexpected response from LM Studio: '
                f'{json.dumps(response)[:500]}') from None
        return text


class OllamaBackend(LocalServerBackend):
    name = 'Ollama'

    def check(self, timeout: float = 5) -> str:
        try:
            if self.model:
                http_json(f'{self.base_url}/api/tags', timeout=timeout)
                return self.model
            # Prefer a model that is already loaded in memory.
            running = http_json(f'{self.base_url}/api/ps',
                                timeout=timeout).get('models', [])
            if running:
                self.model = running[0].get('name') or running[0]['model']
                return self.model
            installed = http_json(f'{self.base_url}/api/tags',
                                  timeout=timeout).get('models', [])
        except (urllib.error.URLError, OSError) as error:
            raise self.unreachable_error(error) from None
        if not installed:
            raise LocalServerError(
                'Ollama has no models. Pull a vision model with '
                '`ollama pull <model>`, or type a model name in the '
                '"Model name" field.')
        self.model = installed[0].get('name') or installed[0]['model']
        return self.model

    def caption(self, image_b64, user_prompt, system_prompt, max_tokens,
                temperature, timeout=600) -> str:
        messages = []
        if system_prompt.strip():
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': user_prompt,
                         'images': [image_b64]})
        payload = {'model': self.model, 'messages': messages,
                   'stream': False,
                   'options': {'temperature': temperature,
                               'num_predict': max_tokens}}
        try:
            response = http_json(f'{self.base_url}/api/chat', payload,
                                 timeout=timeout)
        except (urllib.error.URLError, OSError) as error:
            raise self.unreachable_error(error) from None
        if 'error' in response:
            raise LocalServerError(f'Ollama error: {response["error"]}')
        return response.get('message', {}).get('content') or ''


class LocalServerModel(AutoCaptioningModel):
    """Base class for models served by a local server."""
    backend_class = LocalServerBackend
    url_key = ''
    model_key = ''

    def __init__(self, captioning_thread_, caption_settings: dict):
        super().__init__(captioning_thread_, caption_settings)
        server_settings = caption_settings.get('local_server_settings', {})
        self.server_settings = server_settings
        self.backend = self.backend_class(
            server_settings.get(self.url_key, ''),
            server_settings.get(self.model_key, ''))
        self.system_prompt = server_settings.get('system_prompt', '')
        self.max_tokens = server_settings.get('max_tokens', 1024)
        self.temperature = server_settings.get('temperature', 0.7)
        self.split_tags = server_settings.get('split_tags', True)

    def get_error_message(self) -> str | None:
        if not self.backend.base_url:
            return f'Enter the {self.backend.name} server URL.'
        return None

    def load_processor_and_model(self):
        self.thread.clear_console_text_edit_requested.emit()
        print(f'Connecting to {self.backend.name} at '
              f'{self.backend.base_url}...')
        model_name = self.backend.check()
        print(f'Using {self.backend.name} model: {model_name}')

    def get_captioning_message(self, are_multiple_images_selected: bool,
                               captioning_start_datetime: datetime) -> str:
        message = (f'Captioning with {self.backend.name} '
                   f'(model: {self.backend.model}')
        if are_multiple_images_selected:
            start = self.get_captioning_start_datetime_string(
                captioning_start_datetime)
            message += f', start time: {start}'
        return message + ')...'

    @staticmethod
    def get_default_prompt() -> str:
        return DEFAULT_USER_PROMPT

    def get_model_inputs(self, image_prompt: str, image: Image) -> dict:
        try:
            image_b64 = encode_image(image.path)
        except OSError as error:
            # Let the captioning thread skip unreadable images.
            from PIL import UnidentifiedImageError
            raise UnidentifiedImageError(str(error)) from None
        return {'image_b64': image_b64}

    def generate_caption(self, model_inputs: dict,
                         image_prompt: str) -> tuple[str, str]:
        user_prompt = image_prompt or DEFAULT_USER_PROMPT
        raw_text = self.backend.caption(
            model_inputs['image_b64'], user_prompt, self.system_prompt,
            self.max_tokens, self.temperature)
        text = strip_think(raw_text)
        if not text:
            print('Warning: the model returned an empty caption. If it is a '
                  'reasoning model, increase "Max tokens".')
        separator = self.thread.tag_separator
        if self.split_tags:
            caption = clean_tag_list(text, separator)
        else:
            caption = ' '.join(text.split())
        if self.caption_start.strip() and not caption.startswith(
                self.caption_start.strip()):
            joiner = separator if self.split_tags else ' '
            caption = f'{self.caption_start.strip()}{joiner}{caption}'
        return caption, caption


class LmStudioModel(LocalServerModel):
    backend_class = LmStudioBackend
    url_key = 'lm_studio_url'
    model_key = 'lm_studio_model'


class OllamaModel(LocalServerModel):
    backend_class = OllamaBackend
    url_key = 'ollama_url'
    model_key = 'ollama_model'
