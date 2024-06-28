# configs
port = 8000
model_ids = ['THUDM/cogvlm2-llama3-chat-19B-int4'] # see models.py

# ----

# inspired by https://github.com/ollama/ollama


from fastapi import FastAPI
from pydantic import BaseModel
import sys
import uvicorn
import requests
import json
from PIL import Image as PilImage

app = FastAPI()
_model_id = ""
_model = None
_processor = None

class TextInput(BaseModel):
    prompt: str
    img_path: str

@app.get("/")
async def hello():
    return "Hello"

@app.get("/run/{model_id:path}")
async def run(model_id: str):
    return { "status": "success" }

@app.post("/prompt/")
async def prompt(input: TextInput):
    pil_image = PilImage.open(input.img_path)
    return { "text": input.prompt[::-1] }

def run_cli():
    welcome = "Send a message (/? for help)"
    print(welcome)
    text_input = ""
    while True:
        try:
            text_input = input(">>>")
            if text_input == "": continue
            response = requests.post(f"http://127.0.0.1:{port}/prompt/", json={ "prompt": text_input, "img_path": "images/icon.png" })
            if response.status_code == 200:
                print(response.json()["text"])
            else:
                print(f"Error: {response.status_code} '{response.text}'")
        except KeyboardInterrupt:
            if text_input == "":
                print("Use Ctrl + d or /bye to exit.")
        except EOFError:
            break

if __name__ == "__main__":
    appcommand = "python run_server.py"
    appname = "taggui server"
    commands = ["serve", "run"]
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
        _model_id = sys.argv[2]
        if not _model_id in model_ids:
            print("use one of:\n" + "\n".join(model_ids))
            quit()

        response = requests.get(f"http://127.0.0.1:{port}/run/{_model_id}")
        if response.status_code != 200:
            print(run_error)
            quit()
        run_cli()
