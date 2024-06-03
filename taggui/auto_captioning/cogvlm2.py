import torch
from PIL import Image as PilImage
from torchvision import transforms

LANGUAGE_TOKEN_TYPE_ID = 0
VISION_TOKEN_TYPE_ID = 1


def get_cogvlm2_inputs(model, processor, text: str, pil_image: PilImage,
                       device: torch.device, dtype_argument: dict) -> dict:
    image_size = model.config.vision_config['image_size']
    patch_size = model.config.vision_config['patch_size']
    vision_tokens_count = ((image_size // patch_size // 2)
                           * (image_size // patch_size // 2) + 2)
    input_ids = [processor.bos_token_id]
    token_type_ids = [LANGUAGE_TOKEN_TYPE_ID]
    processor.pad_token_id = 128002
    input_ids += [processor.pad_token_id] * vision_tokens_count
    token_type_ids += [VISION_TOKEN_TYPE_ID] * vision_tokens_count
    text_ids = processor.encode(text, add_special_tokens=False)
    input_ids += text_ids
    token_type_ids += [LANGUAGE_TOKEN_TYPE_ID] * len(text_ids)
    attention_mask = [1] * len(input_ids)
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
    inputs = {
        'input_ids': torch.tensor(input_ids).unsqueeze(0).to(device),
        'token_type_ids': torch.tensor(token_type_ids).unsqueeze(0).to(device),
        'attention_mask': torch.tensor(attention_mask).unsqueeze(0).to(device),
        'images': [[image.to(device, **dtype_argument)]]
    }
    return inputs
