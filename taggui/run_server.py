# configs
appname = "taggui server"
port = 11435 # Ollama port=11434

# ----

# inspired by
# https://github.com/ollama/ollama
# https://github.com/ollama/ollama/blob/main/docs/api.md

import base64
from fastapi import FastAPI, Request
from pydantic import BaseModel
import sys
import uvicorn
import requests
from io import BytesIO
from PIL import Image as PilImage
from PIL.ImageOps import exif_transpose

from auto_captioning.captioning_core import CaptioningCore
from auto_captioning.models import MODELS

app = FastAPI()
caption_settings = {
    'model': "",
    'prompt': "",
    'caption_start': "",
    'caption_position': "",
    'device': "cuda:0",
    'gpu_index': 0,
    'load_in_4_bit': True,
    'remove_tag_separators': True,
    'bad_words': "",
    'forced_words': "",
    'generation_parameters': {
        'min_new_tokens': 1,
        'max_new_tokens': 100,
        'num_beams': 1,
        'length_penalty': 1,
        'do_sample': False,
        'temperature': 1,
        'top_k': 50,
        'top_p': 1,
        'repetition_penalty': 1,
        'no_repeat_ngram_size': 3,
    },
    'wd_tagger_settings': {
        'show_probabilities': True,
        'min_probability': 0.4,
        'max_tags': 30,
        'tags_to_exclude': "",
    }
}
tag_separator = ","
models_directory_path = None
core = CaptioningCore(caption_settings, tag_separator, models_directory_path)

class TextInput(BaseModel):
    prompt: str
    img_path: str

@app.get("/")
async def index():
    return appname

@app.post("/api/generate")
async def prompt(request: Request):
    caption = ""
    try:
        caption_settings = await request.json()
        if "images" not in caption_settings: raise Exception("missing 'images'")
        core.caption_settings.update(caption_settings)
        if core.device == None or core.model == None or core.processor == None or core.model_type == None:
            core.start_captioning()
        if len(caption_settings["images"]) > 0:
            img_bytes = base64.b64decode(caption_settings["images"][0])
            pil_image = PilImage.open(BytesIO(img_bytes))
            pil_image = exif_transpose(pil_image)
            success, msg, caption = core.run_captioning(pil_image)
            if not success: raise Exception(msg)
    except Exception as e:
        return { "type": "error", "msg": str(e) }
    return { "type": "generate", "response": caption }

def run_cli():
    welcome = "Send a message path/to/image.png (/? for help)"
    cli_usage = """
Available Commands:
  /bye            Exit
  /?, /help       Help for a command
"""
    print(welcome)
    text_input = ""
    while True:
        try:
            text_input = input(">>> ")
            if text_input == "": continue
            if text_input == "/bye": break
            if text_input in ["/?", "/help"]:
                print(cli_usage)
                continue

            i = text_input.rfind(' ')
            if i >= 0:
                img_prompt = text_input[:i]
                img_path = text_input[i + 1:]
            else:
                img_prompt = ""
                img_path = text_input

            try:
                with open(img_path, 'rb') as img_file:
                    img = PilImage.open(img_file)
                    img.verify()
                    img_file.seek(0)
                    img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            except Exception as e:
                print(e)
                continue

            response = requests.post(f"http://127.0.0.1:{port}/api/generate", json={ "prompt": img_prompt, "images": [str(img_base64)] }).json()
            if response["type"] == "error": raise Exception(response["msg"])
            print(response["response"])
        except KeyboardInterrupt:
            if text_input == "":
                print("Use Ctrl + d or /bye to exit.")
        except EOFError:
            break
        except Exception as e:
            print(e)

if __name__ == "__main__":
    appcommand = "python run_server.py"
    commands = ["serve", "run"]
    models = '\n    '.join(MODELS)
    usage = f"""
Usage:
{appcommand} [command]

Available Commands:
serve       Start {appname}
run         Run a model
"""
    run_usage = f"""
Run a model

Usage:
    {appcommand} run MODEL

Models:
    {models}
"""
    run_error = f"could not connect to {appname}, is it running?"

    if len(sys.argv) <= 1:
        print(usage)
        quit()

    command = sys.argv[1]
    if not command in commands:
        print(usage)
        quit()

    if command == "serve":
        uvicorn.run(app, host="127.0.0.1", port=port)

    if command == "run":
        if len(sys.argv) <= 2:
            print(run_usage)
            quit()
        model_id = sys.argv[2]
        if not model_id in MODELS:
            print(f"Unknown model_id='{model_id}'. use one of:\n{models}")
            quit()

        try:
            print(f"Loading {model_id}...")

            response = requests.post(f"http://127.0.0.1:{port}/api/generate", json={ "model": model_id, "images": [] }).json()
            if response["type"] == "error": raise Exception(response["msg"])
        except Exception as e:
            print(e)
            quit()

        run_cli()
