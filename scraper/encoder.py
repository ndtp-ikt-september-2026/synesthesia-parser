'''
ML vectorization service wrapping MiniLM-L12-v2 with thread-safe singleton.
'''

import threading
from typing import List, Optional
from sentence_transformers import SentenceTransformer


class InstrumentEncoder:
    '''
    Thread-safe lazy-loading singleton for local 384-dimensional vector encoding.
    '''
    _instance: Optional['InstrumentEncoder'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'InstrumentEncoder':
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InstrumentEncoder, cls).__new__(cls)
                cls._instance._model = None
                cls._instance._model_lock = threading.Lock()
        return cls._instance

    @property
    def is_loaded(self) -> bool:
        '''
        Check if model weights are loaded in memory.
        '''
        return self._model is not None

    def load_model(self) -> None:
        '''
        Explicitly load model weights into memory if not already loaded.
        '''
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = SentenceTransformer(
                        'paraphrase-multilingual-MiniLM-L12-v2',
                        device='cpu'
                    )

    def encode_instrument(self, text: str) -> List[float]:
        '''
        Computes a 384-dimensional normalized float list from deterministic text prompt.
        '''
        if self._model is None:
            self.load_model()

        if not text or not text.strip():
            return [0.0] * 384

        embedding = self._model.encode(
            text.strip(),
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return [float(x) for x in embedding]
