import torch
import torch.nn.functional as F


class BackgroundColor:
    """
    Apply a consistent background color to a batch of images using a mask.
    Optimized for Video Matting by keeping all operations as vectorized
    PyTorch tensors on the GPU/Device.
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),  # [Batch, Height, Width, Channels]
                "mask": ("MASK",),  # [Batch, Height, Width]
                "red": ("INT", {"default": 0, "min": 0, "max": 255}),
                "green": ("INT", {"default": 0, "min": 0, "max": 255}),
                "blue": ("INT", {"default": 0, "min": 0, "max": 255}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "apply_background"
    CATEGORY = "Matting/Utils"

    def apply_background(self, image, mask, red, green, blue):
        # 1. Normalize Colors to 0-1 range and move to device
        # Shape: [1, 1, 1, 3] to broadcast over the image batch
        color = (
            torch.tensor([red, green, blue], device=image.device, dtype=image.dtype)
            / 255.0
        )
        color = color.view(1, 1, 1, 3)

        # 2. Prepare Mask
        # Standardize mask dimensions to [Batch, Height, Width]
        if mask.dim() == 2:
            mask = mask.unsqueeze(0)

        # Resize mask if it doesn't match image dimensions (common in Video workflows)
        # Expected image shape: [B, H, W, C]
        # Expected mask shape: [B, H, W]
        if mask.shape[-2:] != image.shape[1:3]:
            # Interpolate expects [Batch, Channels, Height, Width]
            mask = mask.unsqueeze(1)
            mask = F.interpolate(
                mask, size=image.shape[1:3], mode="bilinear", align_corners=False
            )
            mask = mask.squeeze(1)

        # Broadcast mask to match image channels
        # Mask: [B, H, W] -> [B, H, W, 1]
        mask = mask.unsqueeze(-1)

        # Handle batch size differences if necessary (broadcasting usually handles this,
        # but if mask batch size is 1 and image is N, or vice versa, PyTorch handles it automatically)

        # 3. Composite (Vectorized calculation)
        # result = Foreground * Mask + Background * (1 - Mask)
        inverse_mask = 1.0 - mask
        result = image * mask + color * inverse_mask

        return (result,)


NODE_CLASS_MAPPINGS = {"BackgroundColor": BackgroundColor}

NODE_DISPLAY_NAME_MAPPINGS = {"BackgroundColor": "Background Color (Matting)"}
