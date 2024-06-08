from PIL import Image as PilImage
from torchvision import transforms

class DebugProcessor:
    def __init__(self):
        pass

    def batch_decode(self, generated_token_ids: list[str], skip_special_tokens: bool) -> list[str]:
        return generated_token_ids

    def tokenizer(self, words: list[str], add_special_tokens: bool) -> dict[str, list[str]]:
        return { "input_ids": words }

class DebugModel:
    def __init__(self):
        pass

    def eval(self):
        pass

def get_debug_model_inputs(model: DebugModel, processor: DebugProcessor, text: str, pil_image: PilImage):
    image_size = 1344
    transform = transforms.Compose([
        transforms.Resize(
            (image_size, image_size),
            interpolation=transforms.InterpolationMode.BICUBIC
        ),
        transforms.ToTensor(),
        transforms.Normalize((0.48145466, 0.4578275, 0.40821073),
                             (0.26862954, 0.26130258, 0.27577711))
    ])
    image = transform(pil_image)
