"""
OpenCLIP Embedding Pipeline for Video Frames
"""
import torch
import numpy as np
from PIL import Image
import open_clip
from typing import List, Union
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ClipEmbedder:
    """
    OpenCLIP-based embedder for generating semantic embeddings from video frames and text queries.
    Uses ViT-B-32 model pretrained on LAION-2B for joint image-text embeddings.
    """
    
    def __init__(self, model_name: str = 'ViT-B-32', pretrained: str = 'laion2b_s34b_b79k', device: str = None):
        """
        Initialize the OpenCLIP model and preprocessing transforms.
        
        Args:
            model_name: The CLIP model architecture to use
            pretrained: The pretrained weights to load
            device: Device to run inference on ('cuda', 'cpu', or None for auto)
        """
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Initializing OpenCLIP model {model_name} on {self.device}")
        
        # Set environment variables for safer model loading on ARM64
        os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
        
        # Disable MKL and other acceleration libraries that can cause segfaults on ARM64
        torch.backends.mkldnn.enabled = False
        
        try:
            # Create model without pretrained weights first
            logger.info(f"Creating model architecture...")
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                model_name, 
                pretrained=pretrained,
                device=self.device,
                precision='fp32'  # Use fp32 for better compatibility
            )
            self.model.eval()
            self.tokenizer = open_clip.get_tokenizer(model_name)
            
            # Get embedding dimension
            with torch.no_grad():
                dummy_text = self.tokenizer(["test"])
                dummy_embedding = self.model.encode_text(dummy_text.to(self.device))
                self.embedding_dim = dummy_embedding.shape[1]
            
            logger.info(f"Model initialized. Embedding dimension: {self.embedding_dim}")
        except Exception as e:
            logger.error(f"Failed to initialize model: {e}")
            raise
    
    def encode_image(self, image: Union[Image.Image, np.ndarray, str]) -> np.ndarray:
        """
        Generate embedding for a single image.
        
        Args:
            image: PIL Image, numpy array, or path to image file
            
        Returns:
            Normalized embedding vector as numpy array
        """
        if isinstance(image, str):
            image = Image.open(image).convert('RGB')
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image).convert('RGB')
        
        # Preprocess and encode
        with torch.no_grad():
            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
            embedding = self.model.encode_image(image_tensor)
            # Normalize embedding
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        
        return embedding.cpu().numpy().flatten()
    
    def encode_images(self, images: List[Union[Image.Image, np.ndarray, str]]) -> np.ndarray:
        """
        Generate embeddings for multiple images in batch.
        
        Args:
            images: List of PIL Images, numpy arrays, or image paths
            
        Returns:
            Array of normalized embedding vectors
        """
        processed_images = []
        for img in images:
            if isinstance(img, str):
                img = Image.open(img).convert('RGB')
            elif isinstance(img, np.ndarray):
                img = Image.fromarray(img).convert('RGB')
            processed_images.append(self.preprocess(img))
        
        # Stack and encode
        image_batch = torch.stack(processed_images).to(self.device)
        
        with torch.no_grad():
            embeddings = self.model.encode_image(image_batch)
            # Normalize embeddings
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
        
        return embeddings.cpu().numpy()
    
    def encode_text(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        Generate embedding for text query.
        
        Args:
            text: Text string or list of text strings
            
        Returns:
            Normalized embedding vector(s) as numpy array
        """
        if isinstance(text, str):
            text = [text]
        
        with torch.no_grad():
            text_tokens = self.tokenizer(text).to(self.device)
            embeddings = self.model.encode_text(text_tokens)
            # Normalize embeddings
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
        
        result = embeddings.cpu().numpy()
        return result[0] if len(text) == 1 else result
    
    def compute_clip_embedding(self, frames: List[np.ndarray]) -> np.ndarray:
        """
        Compute averaged clip embedding from multiple frames.
        
        For a 10-second clip with 1 frame sampled per second, this averages
        all 10 frame embeddings to create a single clip-level embedding.
        
        Args:
            frames: List of frame arrays (numpy arrays in RGB format)
            
        Returns:
            Averaged embedding vector
        """
        if not frames:
            raise ValueError("No frames provided for embedding computation")
        
        # Generate embeddings for all frames
        frame_embeddings = self.encode_images(frames)
        
        # Average the embeddings
        clip_embedding = np.mean(frame_embeddings, axis=0)
        
        # Renormalize
        clip_embedding = clip_embedding / np.linalg.norm(clip_embedding)
        
        return clip_embedding
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (0-1)
        """
        return float(np.dot(embedding1, embedding2))


# Model configurations for different accuracy/speed tradeoffs
MODEL_CONFIGS = {
    'standard': {
        'model_name': 'ViT-B-32',
        'pretrained': 'laion2b_s34b_b79k',
        'description': 'Fast, good accuracy (512-dim)'
    },
    'advanced': {
        'model_name': 'ViT-L-14', 
        'pretrained': 'laion2b_s32b_b82k',
        'description': 'Slower, better accuracy (768-dim)'
    },
    'high_accuracy': {
        'model_name': 'ViT-H-14',
        'pretrained': 'laion2b_s32b_b79k',
        'description': 'Slowest, best accuracy (1024-dim)'
    }
}

# Singleton instances for reuse across the application
_embedders = {}


def get_embedder(model_key: str = 'standard') -> ClipEmbedder:
    """
    Get or create an embedder instance for the specified model.
    
    Args:
        model_key: One of 'standard', 'advanced', 'high_accuracy'
        
    Returns:
        ClipEmbedder instance configured for the specified model
    """
    if model_key not in _embedders:
        if model_key not in MODEL_CONFIGS:
            logger.warning(f"Unknown model key '{model_key}', using standard")
            model_key = 'standard'
        
        config = MODEL_CONFIGS[model_key]
        logger.info(f"Creating embedder with config: {config}")
        _embedders[model_key] = ClipEmbedder(
            model_name=config['model_name'],
            pretrained=config['pretrained']
        )
    
    return _embedders[model_key]


def get_embedder_for_mode(search_mode: str) -> ClipEmbedder:
    """
    Get appropriate embedder based on search mode.
    
    Args:
        search_mode: One of 'clip', 'yolo_hybrid', 'advanced_clip'
        
    Returns:
        ClipEmbedder instance appropriate for the search mode
    """
    if search_mode == 'advanced_clip':
        return get_embedder('advanced')
    else:
        return get_embedder('standard')
